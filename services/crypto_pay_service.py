import json
import hashlib
import hmac
import logging
import time
import requests
from datetime import datetime, timedelta

from config import Config
from database.connection import SessionLocal
from database.models import Payment as DBPayment, Subscription, Tariff, User
from services.telegram_channel_service import TelegramChannelService
from services.purchase_notification_service import PurchaseNotificationService

logger = logging.getLogger(__name__)

CRYPTOPAY_API_BASE = {
    "mainnet": "https://pay.crypt.bot/api",
    "testnet": "https://testnet-pay.crypt.bot/api",
}


class CryptoPayService:
    def __init__(self, telegram_channel_service: TelegramChannelService = None,
                 purchase_notification_service: PurchaseNotificationService = None):
        self.api_token = Config.CRYPTOPAY_API_TOKEN
        self.network = getattr(Config, "CRYPTOPAY_NETWORK", "mainnet")
        self.api_base = CRYPTOPAY_API_BASE.get(self.network, CRYPTOPAY_API_BASE["mainnet"])
        self.telegram_channel_service = telegram_channel_service
        self.purchase_notification_service = purchase_notification_service

        if not self.is_available:
            logger.warning("CryptoPayService: CRYPTOPAY_API_TOKEN не задан, крипто-платежи недоступны")
        else:
            logger.info(f"CryptoPayService инициализирован (network={self.network})")

    @property
    def is_available(self) -> bool:
        """Returns True if CryptoPay is configured and available."""
        return bool(self.api_token)

    def create_invoice(self, user_id: int, tariff_id: int, amount: float,
                       description: str | None = None) -> dict | None:
        """
        Creates a CryptoPay invoice for the given tariff.
        Returns dict with invoice_id and pay_url, or None on failure.
        """
        db = SessionLocal()
        try:
            # --- Проверка тарифа ---
            tariff = db.query(Tariff).get(tariff_id)
            if not tariff:
                logger.error(f"CryptoPay create_invoice: тариф {tariff_id} не найден")
                return None
            if not tariff.is_active:
                logger.error(f"CryptoPay create_invoice: тариф {tariff_id} неактивен")
                return None

            # --- Проверка пользователя ---
            user = db.query(User).filter(User.telegram_id == user_id).first()
            if not user:
                logger.error(f"CryptoPay create_invoice: пользователь {user_id} не найден")
                return None

            # --- Подготовка данных для CryptoPay API ---
            bot_name = getattr(Config, "BOT_NAME", "TelegramBot").strip("@")
            payload_data = json.dumps({"user_id": user_id, "tariff_id": tariff_id})

            request_body = {
                "currency_type": "fiat",
                "fiat": "RUB",
                "amount": str(amount),
                "description": description or f"Подписка на тариф '{tariff.name}'",
                "payload": payload_data,
                "paid_btn_name": "callback",
                "paid_btn_url": f"https://t.me/{bot_name}",
            }

            headers = {
                "Crypto-Pay-API-Token": self.api_token,
                "Content-Type": "application/json",
            }

            # --- Запрос к CryptoPay API с retry ---
            result = self._request_with_retry(
                method="POST",
                url=f"{self.api_base}/createInvoice",
                headers=headers,
                json_body=request_body,
            )

            if result is None:
                return None

            # --- Парсинг ответа ---
            if not result.get("ok"):
                error_msg = result.get("error", {}).get("name", "Unknown error")
                logger.error(f"CryptoPay API вернул ошибку: {error_msg}")
                return None

            invoice_data = result.get("result", {})
            invoice_id = invoice_data.get("invoice_id")
            pay_url = invoice_data.get("mini_app_invoice_url") or invoice_data.get("bot_invoice_url")

            if not invoice_id or not pay_url:
                logger.error(f"CryptoPay API: некорректный ответ, нет invoice_id или pay_url")
                return None

            # --- Сохраняем платёж в БД ---
            db_payment = DBPayment(
                user_id=user.telegram_id,
                amount=amount,
                status="pending",
                payment_provider="cryptopay",
                cryptopay_invoice_id=str(invoice_id),
            )
            db.add(db_payment)
            db.commit()

            logger.info(
                f"✅ CryptoPay инвойс {invoice_id} создан для пользователя {user_id} "
                f"на {amount}₽ (тариф: {tariff.name})"
            )

            return {
                "invoice_id": invoice_id,
                "pay_url": pay_url,
            }

        except Exception as e:
            logger.exception(f"CryptoPay create_invoice: непредвиденная ошибка: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """
        Verifies CryptoPay webhook signature using HMAC-SHA-256.
        The secret is SHA-256 hash of the API token.
        """
        if not self.api_token:
            return False
        secret = hashlib.sha256(self.api_token.encode()).digest()
        expected = hmac.HMAC(secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_webhook(self, data: dict) -> bool:
        """
        Processes a verified CryptoPay webhook payload.
        Updates payment status, activates subscription if paid.
        """
        db = SessionLocal()
        try:
            invoice_id = str(data.get("invoice_id", ""))
            status = data.get("status", "")

            if not invoice_id:
                logger.warning("CryptoPay webhook: отсутствует invoice_id в payload")
                return True

            # --- Ищем платёж в БД ---
            payment = db.query(DBPayment).filter_by(cryptopay_invoice_id=invoice_id).first()
            if not payment:
                logger.warning(f"CryptoPay webhook: инвойс {invoice_id} не найден в базе")
                return True

            # --- Дублирующий webhook (уже обработан) ---
            if payment.status == "succeeded":
                logger.info(f"CryptoPay webhook: инвойс {invoice_id} уже обработан, пропускаем")
                return True

            if status != "paid":
                logger.info(f"CryptoPay webhook: инвойс {invoice_id} статус={status}, не paid")
                return True

            # --- Обновляем статус платежа ---
            payment.status = "succeeded"
            payment.updated_at = datetime.utcnow()

            # --- Извлекаем user_id и tariff_id из payload ---
            payload_str = data.get("payload", "{}")
            try:
                payload_data = json.loads(payload_str)
            except (json.JSONDecodeError, TypeError):
                payload_data = {}

            user_id = payload_data.get("user_id") or payment.user_id
            tariff_id = payload_data.get("tariff_id")

            if tariff_id:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            else:
                tariff = None

            if tariff:
                now = datetime.utcnow()

                # --- Активация/продление подписки ---
                existing_sub = (
                    db.query(Subscription)
                    .filter_by(user_id=user_id)
                    .order_by(Subscription.created_at.desc())
                    .first()
                )

                if existing_sub:
                    if existing_sub.end_date and existing_sub.end_date > now:
                        existing_sub.end_date = existing_sub.end_date + timedelta(
                            days=tariff.duration_days or 36500
                        )
                    else:
                        existing_sub.end_date = now + timedelta(days=tariff.duration_days or 36500)
                        existing_sub.start_date = now

                    existing_sub.is_active = True
                    existing_sub.reminder_sent = False
                    payment.subscription_id = existing_sub.id
                    logger.info(
                        f"Подписка {existing_sub.id} продлена для пользователя {user_id} до {existing_sub.end_date}"
                    )
                else:
                    end_date = now + timedelta(days=tariff.duration_days or 36500)
                    subscription = Subscription(
                        user_id=user_id,
                        tariff_id=tariff_id,
                        start_date=now,
                        end_date=end_date,
                        is_active=True,
                    )
                    db.add(subscription)
                    db.flush()
                    payment.subscription_id = subscription.id
                    logger.info(f"Создана новая подписка для пользователя {user_id}")

                # --- Обновляем total_spent ---
                user = db.query(User).filter(User.telegram_id == user_id).first()
                if user:
                    user.total_spent = (user.total_spent or 0.0) + float(payment.amount)

                    # --- Уведомление о покупке ---
                    if self.purchase_notification_service:
                        try:
                            user_info = {
                                "username": user.username,
                                "first_name": user.first_name,
                                "last_name": user.last_name,
                            }
                            self.purchase_notification_service.send_purchase_notification(
                                user_id=user_id,
                                user_info=user_info,
                                tariff_name=tariff.name,
                                amount=float(payment.amount),
                                payment_id=f"crypto_{invoice_id}",
                            )
                        except Exception as e:
                            logger.error(
                                f"Ошибка отправки уведомления о покупке: {e}", exc_info=True
                            )

                # --- Доступ к каналу ---
                if self.telegram_channel_service:
                    try:
                        self.telegram_channel_service.add_user_to_channel(user_id)
                        logger.info(f"Доступ к каналу выдан пользователю {user_id}")
                    except Exception as e:
                        logger.error(f"Ошибка доступа к каналу для {user_id}: {e}")

            db.commit()
            logger.info(f"✅ CryptoPay платёж {invoice_id} успешно обработан")
            return True

        except Exception as e:
            logger.exception(f"CryptoPay process_webhook: ошибка: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def _request_with_retry(self, method: str, url: str, headers: dict,
                            json_body: dict, max_retries: int = 3, delay: float = 1.0):
        """
        Makes an HTTP request with exponential backoff retry on connection errors.
        Returns parsed JSON response or None on failure.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"CryptoPay API: попытка {attempt + 1}/{max_retries} — {method} {url}")
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_body,
                    timeout=(10, 30),
                )
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt == max_retries - 1:
                    logger.error(
                        f"CryptoPay API: ошибка соединения после {max_retries} попыток: {e}"
                    )
                    return None
                logger.warning(
                    f"CryptoPay API: ошибка соединения (попытка {attempt + 1}), повтор через {delay}с: {e}"
                )
                time.sleep(delay)
                delay *= 2
            except requests.exceptions.HTTPError as e:
                logger.error(f"CryptoPay API: HTTP ошибка: {e} — {e.response.text if e.response else ''}")
                # Пытаемся вернуть JSON с ошибкой от API
                try:
                    return e.response.json()
                except Exception:
                    return None
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    logger.error(f"CryptoPay API: ошибка запроса после {max_retries} попыток: {e}")
                    return None
                logger.warning(
                    f"CryptoPay API: ошибка запроса (попытка {attempt + 1}), повтор через {delay}с: {e}"
                )
                time.sleep(delay)
                delay *= 2
            except Exception as e:
                logger.error(f"CryptoPay API: непредвиденная ошибка: {e}")
                return None
        return None
