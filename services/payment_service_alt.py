import uuid
import logging
import time
from datetime import datetime, timedelta

from yookassa import Configuration, Payment
from yookassa.domain.exceptions import BadRequestError, ApiError
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

from config import Config
from database.models import Payment as DBPayment, Subscription, Tariff, User, PromoCode
from database.connection import SessionLocal
from services.telegram_channel_service import TelegramChannelService
from services.marathon_service import MarathonService
from services.purchase_notification_service import PurchaseNotificationService

logger = logging.getLogger(__name__)

# Настройка requests с таймаутами
session = requests.Session()
session.timeout = (10, 30)

def _sanitize_env_value(value):
    return str(value).strip() if value is not None else ""

_SHOP_ID = _sanitize_env_value(Config.YOOKASSA_SHOP_ID)
_SECRET_KEY = _sanitize_env_value(Config.YOOKASSA_SECRET_KEY)

if _SHOP_ID and not _SHOP_ID.isdigit():
    raise ValueError("YOOKASSA_SHOP_ID должен содержать только цифры без пробелов")

Configuration.configure(_SHOP_ID, _SECRET_KEY)

def _make_yookassa_request_with_retry(request_func, max_retries=3, delay=1):
    for attempt in range(max_retries):
        try:
            logger.info(f"Yookassa API: попытка {attempt + 1}/{max_retries}")
            return request_func()
        except (ConnectionError, Timeout) as e:
            if attempt == max_retries - 1:
                logger.error(f"Yookassa API: ошибка соединения после {max_retries} попыток: {e}")
                raise ConnectionError(f"Не удалось подключиться к Yookassa API: {e}")
            else:
                time.sleep(delay)
                delay *= 2
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                logger.error(f"Yookassa API: ошибка запроса после {max_retries} попыток: {e}")
                raise ConnectionError(f"Ошибка запроса к Yookassa API: {e}")
            else:
                time.sleep(delay)
                delay *= 2
        except Exception as e:
            logger.error(f"Yookassa API: непредвиденная ошибка: {e}")
            raise e

class PaymentService:
    def __init__(self, telegram_channel_service: TelegramChannelService = None, purchase_notification_service: PurchaseNotificationService = None):
        self.shop_id = Config.YOOKASSA_SHOP_ID
        self.secret_key = Config.YOOKASSA_SECRET_KEY
        self.telegram_channel_service = telegram_channel_service
        self.purchase_notification_service = purchase_notification_service
        logger.info(f"PaymentService инициализирован (Shop ID: {self.shop_id})")

    def create_payment(
        self,
        user_id: int,
        tariff_id: int,
        amount: float,
        description: str | None = None,
        customer_email: str | None = None,
        item_description: str | None = None,
        metadata: dict | None = None,
    ):
        db = SessionLocal()
        try:
            # --- Проверка суммы ---
            try:
                amount = float(amount)
            except Exception:
                raise ValueError("Некорректная сумма оплаты: amount должен быть числом")
            if amount <= 0:
                raise ValueError("Сумма оплаты должна быть больше 0")

            # --- Проверка тарифа ---
            tariff = db.query(Tariff).get(tariff_id)
            if not tariff:
                raise ValueError("Тариф не найден")
            if not tariff.is_active:
                raise ValueError("Тариф неактивен")

            # --- Проверка пользователя ---
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                raise ValueError("Пользователь не найден")

            # --- Проверка активной подписки ---
            active_sub = db.query(Subscription).filter(
                Subscription.user_id == user.telegram_id, Subscription.is_active.is_(True)
            ).first()
            if active_sub:
                logger.info(f"У пользователя {user_id} уже есть активная подписка")

            # --- Готовим базовые данные платежа ---
            payment_data = {
                "amount": {"value": f"{amount:.2f}", "currency": getattr(tariff, "currency", "RUB")},
                "confirmation": {"type": "redirect", "return_url": f"https://t.me/{Config.BOT_NAME.strip('@')}"},
                "capture": True,
                "description": description or f"Подписка на тариф '{tariff.name}'",
                "metadata": metadata or {"user_id": user.telegram_id, "tariff_id": tariff_id, "tariff_name": tariff.name},
            }

            # --- ✅ FIX: создаём чек всегда (даже если email нет) ---
            customer_email = customer_email or f"user_{user.telegram_id}@example.com"

            payment_data["receipt"] = {
                "customer": {"email": customer_email},
                "items": [
                    {
                        "description": item_description or tariff.name,
                        "quantity": "1.00",  # ✅ FIX: строка, а не int
                        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                        "vat_code": 1,  # 1 = без НДС
                        "payment_subject": "service",  # ✅ FIX: обязательное поле
                        "payment_mode": "full_payment",  # ✅ FIX: обязательное поле
                    }
                ],
            }

            idempotency_key = str(uuid.uuid4())

            logger.info(
                f"Создание платежа YooKassa | user={user_id} | tariff={tariff.name} | amount={amount:.2f} | email={customer_email}"
            )

            # --- Запрос с повторами ---
            payment = _make_yookassa_request_with_retry(
                lambda: Payment.create(payment_data, idempotency_key)
            )

            # --- Сохраняем в БД ---
            db_payment = DBPayment(
                user_id=user.telegram_id,
                subscription_id=None,
                yookassa_payment_id=payment.id,
                amount=amount,
                status=payment.status
            )
            db.add(db_payment)
            db.commit()

            confirmation_url = payment.confirmation.confirmation_url
            logger.info(f"✅ Платёж {payment.id} на {amount}₽ успешно создан для пользователя {user_id}")

            return {
                "payment_id": payment.id,
                "confirmation_url": confirmation_url,
                "status": payment.status
            }

        except (ApiError, BadRequestError) as e:
            logger.error(f"Ошибка ЮKassa: {e}")
            db.rollback()
            raise ValueError(f"Ошибка создания платежа: {e}")
        except (ConnectionError, Timeout) as e:
            logger.error(f"Ошибка соединения с Yookassa: {e}")
            db.rollback()
            raise ValueError("Ошибка соединения с платежной системой. Попробуйте позже.")
        except Exception as e:
            logger.exception(f"Ошибка создания платежа: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    def process_payment_notification(self, payment_id: str, status: str):
        db = SessionLocal()
        try:
            payment = db.query(DBPayment).filter_by(yookassa_payment_id=payment_id).first()
            if not payment:
                logger.warning(f"Платёж {payment_id} не найден в базе")
                return False

            payment.status = status
            payment.updated_at = datetime.utcnow()

            if status == "succeeded":
                logger.info(f"Платёж {payment_id} успешно оплачен")
                yk = _make_yookassa_request_with_retry(lambda: Payment.find_one(payment_id))
                metadata = yk.metadata or {}
                user_id = metadata.get("user_id")
                tariff_id = metadata.get("tariff_id")

                if tariff_id and user_id:
                    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                    if tariff:
                        now = datetime.utcnow()
                        # Ищем любую подписку пользователя (активную или неактивную) для продления
                        existing_sub = db.query(Subscription).filter_by(user_id=user_id).order_by(Subscription.created_at.desc()).first()
                        
                        if existing_sub:
                            # Продлеваем существующую подписку
                            # Если подписка истекла, начинаем отсчет с текущего момента, иначе продлеваем от текущей даты окончания
                            if existing_sub.end_date and existing_sub.end_date > now:
                                # Подписка еще активна - продлеваем от даты окончания
                                existing_sub.end_date = existing_sub.end_date + timedelta(days=tariff.duration_days or 36500)
                            else:
                                # Подписка истекла - начинаем отсчет с текущего момента
                                existing_sub.end_date = now + timedelta(days=tariff.duration_days or 36500)
                                existing_sub.start_date = now
                            
                            # Активируем подписку, если она была неактивна
                            existing_sub.is_active = True
                            existing_sub.reminder_sent = False  # Сбрасываем флаг напоминания
                            payment.subscription_id = existing_sub.id
                            logger.info(f"Подписка {existing_sub.id} продлена для пользователя {user_id} до {existing_sub.end_date}")
                        else:
                            # Создаем новую подписку, если у пользователя нет подписок
                            end_date = now + timedelta(days=tariff.duration_days or 36500)
                            subscription = Subscription(
                                user_id=user_id,
                                tariff_id=tariff_id,
                                start_date=now,
                                end_date=end_date,
                                is_active=True
                            )
                            db.add(subscription)
                            db.flush()
                            payment.subscription_id = subscription.id
                            logger.info(f"Создана новая подписка {subscription.id} для пользователя {user_id}")

                        user = db.query(User).filter(User.telegram_id == user_id).first()
                        if user:
                            user.total_spent = (user.total_spent or 0.0) + float(payment.amount)
                            
                            # Отправляем уведомление о покупке в группу
                            if self.purchase_notification_service:
                                try:
                                    user_info = {
                                        'username': user.username,
                                        'first_name': user.first_name,
                                        'last_name': user.last_name
                                    }
                                    # Получаем промокод из метаданных для уведомления
                                    promocode = metadata.get("promocode")
                                    
                                    self.purchase_notification_service.send_purchase_notification(
                                        user_id=user_id,
                                        user_info=user_info,
                                        tariff_name=tariff.name,
                                        amount=float(payment.amount),
                                        payment_id=payment_id,
                                        promocode=promocode
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка отправки уведомления о покупке в группу: {e}", exc_info=True)

                        promocode = metadata.get("promocode")
                        if promocode:
                            promo = db.query(PromoCode).filter(PromoCode.code == promocode).first()
                            if promo:
                                promo.usage_count = (promo.usage_count or 0) + 1
                                logger.info(f"Промокод {promocode} использован {promo.usage_count} раз")

                        # Обновляем статус пользователя в марафоне (прекращаем рассылки)
                        try:
                            MarathonService.update_user_status(user_id, status='subscribed')
                            logger.info(f"Статус пользователя {user_id} обновлен на 'subscribed'")
                        except Exception as e:
                            logger.error(f"Ошибка обновления статуса пользователя {user_id}: {e}")
                        
                        if self.telegram_channel_service:
                            try:
                                self.telegram_channel_service.add_user_to_channel(user_id)
                                logger.info(f"Доступ к каналу выдан пользователю {user_id}")
                            except Exception as e:
                                logger.error(f"Ошибка доступа к каналу: {e}")

            db.commit()
            return True

        except Exception as e:
            logger.exception(f"Ошибка обработки уведомления: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def check_payment_status(self, payment_id: str):
        try:
            payment = _make_yookassa_request_with_retry(lambda: Payment.find_one(payment_id))
            return payment.status
        except Exception as e:
            logger.error(f"Ошибка проверки статуса: {e}")
            raise ValueError(f"Ошибка проверки статуса платежа: {e}")

    def get_payment_info(self, payment_id: str):
        try:
            payment = _make_yookassa_request_with_retry(lambda: Payment.find_one(payment_id))
            return {
                "id": payment.id,
                "status": payment.status,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "description": getattr(payment, "description", None),
                "metadata": payment.metadata,
                "created_at": payment.created_at,
                "paid": getattr(payment, "paid", None),
                "confirmation_url": getattr(payment.confirmation, "confirmation_url", None)
                if hasattr(payment, 'confirmation') and payment.confirmation else None
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации: {e}")
            raise ValueError(f"Ошибка получения информации о платеже: {e}")
