import json
import hmac
import hashlib
import logging
from flask import Flask, request, jsonify
import telebot # Import telebot
from services.payment_service_alt import PaymentService
from services.telegram_channel_service import TelegramChannelService # Import TelegramChannelService
from services.crypto_pay_service import CryptoPayService
from services.purchase_notification_service import PurchaseNotificationService
from config import Config

logger = logging.getLogger(__name__)

app = Flask(__name__)

bot = telebot.TeleBot(Config.TELEGRAM_BOT_TOKEN) # Initialize bot here
telegram_channel_service = TelegramChannelService(bot) # Initialize TelegramChannelService
payment_service = PaymentService(telegram_channel_service=telegram_channel_service) # Pass channel service to PaymentService
purchase_notification_service = PurchaseNotificationService(bot)
crypto_pay_service = CryptoPayService(
    telegram_channel_service=telegram_channel_service,
    purchase_notification_service=purchase_notification_service
)

@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    """Обрабатывает вебхуки от ЮKassa"""
    try:
        # Получаем данные из запроса
        data = request.get_json()
        
        if not data:
            logger.error("Получен пустой webhook от ЮKassa")
            return jsonify({"error": "Empty webhook"}), 400

        # Проверяем подпись (если настроена)
        # signature = request.headers.get('X-YooKassa-Signature')
        # if signature:
        #     if not verify_signature(data, signature):
        #         logger.error("Неверная подпись webhook")
        #         return jsonify({"error": "Invalid signature"}), 400

        # Обрабатываем уведомление
        event = data.get('event')
        payment_id = data.get('object', {}).get('id')
        
        if not payment_id:
            logger.error("Не найден payment_id в webhook")
            return jsonify({"error": "No payment_id"}), 400

        logger.info(f"Получен webhook: event={event}, payment_id={payment_id}")

        if event == 'payment.succeeded':
            # Обрабатываем успешный платеж
            success = payment_service.process_payment_notification(payment_id, 'succeeded')
            if success:
                logger.info(f"Платеж {payment_id} успешно обработан")
                return jsonify({"status": "success"}), 200
            else:
                logger.error(f"Ошибка обработки платежа {payment_id}")
                return jsonify({"error": "Payment processing failed"}), 500
                
        elif event == 'payment.canceled':
            # Обрабатываем отмененный платеж
            success = payment_service.process_payment_notification(payment_id, 'canceled')
            if success:
                logger.info(f"Платеж {payment_id} отменен")
                return jsonify({"status": "success"}), 200
            else:
                logger.error(f"Ошибка обработки отмены платежа {payment_id}")
                return jsonify({"error": "Payment cancellation failed"}), 500
                
        else:
            logger.info(f"Неизвестное событие webhook: {event}")
            return jsonify({"status": "ignored"}), 200

    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return jsonify({"error": str(e)}), 500

def verify_signature(data, signature):
    """Проверяет подпись webhook (опционально)"""
    # Здесь можно добавить проверку подписи, если она настроена в ЮKassa
    # Пока что возвращаем True
    return True


@app.route('/webhook/cryptopay', methods=['POST'])
def cryptopay_webhook():
    """Processes CryptoPay webhook notifications."""
    try:
        body = request.get_data()
        signature = request.headers.get('crypto-pay-api-signature', '')

        if not crypto_pay_service.verify_webhook_signature(body, signature):
            logger.warning("CryptoPay webhook: invalid signature")
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"status": "ok"}), 200

        update_type = data.get("update_type")

        if update_type == "invoice_paid":
            payload = data.get("payload", {})
            crypto_pay_service.process_webhook(payload)

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Ошибка обработки CryptoPay webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервиса"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
