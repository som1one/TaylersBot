import os
from dotenv import load_dotenv

# Загружаем переменные из local.env
load_dotenv('local.env')

class Config:
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    # Загружается из БД при старте; env — только дефолт для первого запуска
    ADMIN_USER_IDS = [int(x.strip()) for x in os.getenv('ADMIN_USER_IDS', '').split(',') if x.strip()]
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL','postgresql://tg_bot_user:tg_bot_password@postgres:5432/tg_bot_db')
    
    # YooKassa
    YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

    # Telegram Channel ID for premium access
    TELEGRAM_CHANNEL_ID = int(os.getenv("TELEGRAM_CHANNEL_ID", "-1002237839395"))
    TELEGRAM_CHANNEL_JOIN_URL = os.getenv("TELEGRAM_CHANNEL_JOIN_URL", "https://t.me/+gQmmhl_AIIo4MWUy")
    
    # Telegram Group ID for purchase notifications
    TELEGRAM_NOTIFICATIONS_GROUP_ID = os.getenv("TELEGRAM_NOTIFICATIONS_GROUP_ID", None)
    
    # Crypto (ручная оплата)
    CRYPTO_WALLET_ADDRESS = os.getenv("CRYPTO_WALLET_ADDRESS", "")  # Адрес кошелька для оплаты
    CRYPTO_WALLET_NETWORK = os.getenv("CRYPTO_WALLET_NETWORK", "USDT TRC-20")  # Сеть
    CRYPTO_ADMIN_USERNAME = os.getenv("CRYPTO_ADMIN_USERNAME", "")  # @username админа для чеков

    # Bot Settings
    BOT_NAME = os.getenv('BOT_NAME', 'TelegramBot')