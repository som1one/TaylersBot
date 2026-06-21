import uuid
import logging
from datetime import datetime, timedelta

# Импорты YooKassa
from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification
from yookassa.domain.request import PaymentRequest
from yookassa.domain.models.currency import Currency
from yookassa.domain.exceptions import (
    BadRequestError,
    NotFoundError,
    UnauthorizedError,
    ApiError,
    ForbiddenError,
    TooManyRequestsError
)

from config import Config
from database.models import Payment as DbPayment, Subscription, Tariff
from database.connection import SessionLocal

logger = logging.getLogger(__name__)
Configuration.configure(Config.YOOKASSA_SHOP_ID, Config.YOOKASSA_SECRET_KEY)

class PaymentService:
    def __init__(self):
        self.shop_id = Config.YOOKASSA_SHOP_ID
        self.secret_key = Config.YOOKASSA_SECRET_KEY

        # Настройка YooKassa один раз при инициализации
        Configuration.configure(self.shop_id, self.secret_key)

        if not self.shop_id or self.shop_id == 'your_shop_id_here':
            logger.error("YOOKASSA_SHOP_ID не настроен!")
            raise ValueError("YOOKASSA_SHOP_ID не задан в конфиге")

        if not self.secret_key or self.secret_key == 'your_secret_key_here':
            logger.error("YOOKASSA_SECRET_KEY не настроен!")
            raise ValueError("YOOKASSA_SECRET_KEY не задан в конфиге")

    def create_payment(self, user_id: int, tariff_id: int, amount: float, description: str = None):
        """Создает платеж в ЮKassa и возвращает ссылку на оплату"""
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if not tariff:
                raise ValueError("Тариф не найден")

            if not tariff.is_active:
                raise ValueError("Тариф неактивен")

            active_subscription = db.query(Subscription).filter(
                Subscription.user_id == user_id,
                Subscription.is_active == True
            ).first()

            if active_subscription:
                logger.info(f"У пользователя {user_id} уже есть активная подписка")

            payment_request = PaymentRequest(
                amount={
                    "value": str(amount),
                    "currency": Currency.RUB
                },
                confirmation={
                    "type": "redirect",
                    "return_url": f"https://t.me/{Config.BOT_NAME.replace('@', '')}"
                },
                capture=True,
                description=description or f"Подписка на тариф '{tariff.name}'",
                metadata={
                    "user_id": user_id,
                    "tariff_id": tariff_id,
                    "tariff_name": tariff.name
                },
                receipt={
                    "customer": {
                        "email": f"user_{user_id}@bot.com"
                    },
                    "items": [
                        {
                            "description": f"Подписка на тариф '{tariff.name}'",
                            "quantity": "1",
                            "amount": {
                                "value": str(amount),
                                "currency": Currency.RUB
                            },
                            "vat_code": 1,
                            "payment_subject": "service"
                        }
                    ]
                }
            )

            # Создаем платеж через современный API
            payment = Payment.create(payment_request)

            db_payment = DbPayment(
                user_id=user_id,
                subscription_id=None,
                yookassa_payment_id=payment.id,
                amount=amount,
                status=payment.status
            )
            db.add(db_payment)
            db.commit()

            confirmation_url = payment.confirmation.confirmation_url if hasattr(payment.confirmation,
                                                                                'confirmation_url') else None
            if not confirmation_url:
                raise ValueError("Не удалось получить ссылку подтверждения оплаты.")

            logger.info(f"Создан платеж {payment.id} для пользователя {user_id} на сумму {amount}₽")

            return {
                "payment_id": payment.id,
                "confirmation_url": confirmation_url,
                "status": payment.status,
                "amount": amount,
                "tariff_name": tariff.name
            }

        except (BadRequestError, NotFoundError, UnauthorizedError, ApiError) as e:
            logger.error(f"Ошибка ЮKassa: {e}")
            db.rollback()
            raise ValueError(f"Ошибка создания платежа: {e}")
        except Exception as e:
            logger.error(f"Ошибка создания платежа: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

    def process_payment_notification(self, payment_id: str, status: str):
        """Обрабатывает уведомление о платеже от ЮKassa"""
        db = SessionLocal()
        try:
            payment = db.query(DbPayment).filter(DbPayment.yookassa_payment_id == payment_id).first()
            if not payment:
                logger.warning(f"Платеж {payment_id} не найден в базе")
                return False

            payment.status = status
            payment.updated_at = datetime.utcnow()

            if status == "succeeded":
                logger.info(f"Платеж {payment_id} успешно обработан")

                # Получаем информацию о платеже
                yookassa_payment = Payment.find_one(payment_id)
                tariff_id = yookassa_payment.metadata.get("tariff_id")
                user_id = yookassa_payment.metadata.get("user_id")

                if tariff_id and user_id:
                    tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                    if tariff:
                        # Деактивируем старые подписки
                        db.query(Subscription).filter(
                            Subscription.user_id == user_id,
                            Subscription.is_active == True
                        ).update({
                            "is_active": False,
                            "end_date": datetime.utcnow()
                        })

                        # Создаем новую подписку
                        end_date = datetime.utcnow() + timedelta(
                            days=tariff.duration_days) if tariff.duration_days else datetime.utcnow() + timedelta(
                            days=36500)

                        subscription = Subscription(
                            user_id=user_id,
                            tariff_id=tariff_id,
                            start_date=datetime.utcnow(),
                            end_date=end_date,
                            is_active=True
                        )
                        db.add(subscription)
                        db.flush()
                        payment.subscription_id = subscription.id

                        logger.info(f"Создана подписка {subscription.id} для пользователя {user_id}")

            db.commit()
            return True

        except (BadRequestError, NotFoundError, UnauthorizedError, ApiError) as e:
            logger.error(f"Ошибка ЮKassa при обработке платежа {payment_id}: {e}")
            db.rollback()
            return False
        except Exception as e:
            logger.error(f"Ошибка обработки платежа {payment_id}: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def check_payment_status(self, payment_id: str):
        """Проверяет статус платежа в ЮKassa"""
        try:
            payment = Payment.find_one(payment_id)
            return payment.status
        except (BadRequestError, NotFoundError, UnauthorizedError, ApiError) as e:
            logger.error(f"Ошибка проверки статуса платежа {payment_id}: {e}")
            raise e
        except Exception as e:
            logger.error(f"Неожиданная ошибка при проверке статуса платежа {payment_id}: {e}")
            raise e

    def get_payment_info(self, payment_id: str):
        """Получает информацию о платеже"""
        try:
            payment = Payment.find_one(payment_id)
            return {
                "id": payment.id,
                "status": payment.status,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "description": payment.description,
                "metadata": payment.metadata,
                "created_at": payment.created_at,
                "paid": payment.paid
            }
        except (BadRequestError, NotFoundError, UnauthorizedError, ApiError) as e:
            logger.error(f"Ошибка получения информации о платеже {payment_id}: {e}")
            raise e