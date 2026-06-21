import telebot
import threading
import time
from datetime import datetime

from config import Config
from services.payment_service_alt import PaymentService
from services.broadcast_service import BroadcastService
from services.reminder_service import ReminderService
from services.telegram_channel_service import TelegramChannelService
from services.user_service import UserService
from services.notification_service import NotificationService
from services.notification_sender_service import NotificationSenderService
from services.user_activity_service import UserActivityService
from services.marathon_mailing_service import MarathonMailingService
from services.purchase_notification_service import PurchaseNotificationService
from database.connection import SessionLocal, engine
from database.models import Admin, Base

bot = telebot.TeleBot(Config.TELEGRAM_BOT_TOKEN)
telegram_channel_service = TelegramChannelService(bot)
purchase_notification_service = PurchaseNotificationService(bot)
payment_service = PaymentService(
    telegram_channel_service=telegram_channel_service,
    purchase_notification_service=purchase_notification_service
)
broadcast_service = BroadcastService(bot)
reminder_service = ReminderService(broadcast_service)
notification_sender_service = NotificationSenderService(bot)
user_activity_service = UserActivityService(bot)
marathon_mailing_service = MarathonMailingService(bot)


def check_expired_subscriptions_task():
    import logging
    logger = logging.getLogger(__name__)
    
    while True:
        db = SessionLocal()
        try:
            expired_subscriptions = UserService.get_expired_active_subscriptions()
            if expired_subscriptions:
                logger.info(f"[SUBSCRIPTION] Найдено {len(expired_subscriptions)} истекших подписок")
            
            for sub in expired_subscriptions:
                user_id = sub.user_id
                try:
                    logger.info(f"[SUBSCRIPTION] Обработка истекшей подписки {sub.id} для пользователя {user_id}")
                    
                    # Удаляем пользователя из канала
                    removed = telegram_channel_service.remove_user_from_channel(user_id)
                    
                    if removed:
                        # Деактивируем подписку
                        if UserService.mark_subscription_inactive(sub.id):
                            logger.info(f"[SUBSCRIPTION] Пользователь {user_id} удален из канала, подписка {sub.id} деактивирована")
                        else:
                            logger.warning(f"[SUBSCRIPTION] Пользователь {user_id} удален из канала, но не удалось деактивировать подписку {sub.id}")
                    else:
                        logger.warning(f"[SUBSCRIPTION] Не удалось удалить пользователя {user_id} из канала, но деактивируем подписку {sub.id}")
                        # Все равно деактивируем подписку, даже если не удалось удалить из канала
                        UserService.mark_subscription_inactive(sub.id)
                except Exception as e:
                    logger.error(f"[SUBSCRIPTION] Ошибка при обработке подписки {sub.id} для пользователя {user_id}: {e}", exc_info=True)
                    # Пытаемся деактивировать подписку даже при ошибке удаления из канала
                    try:
                        UserService.mark_subscription_inactive(sub.id)
                    except:
                        pass
        except Exception as e:
            logger.error(f"[SUBSCRIPTION ERROR] Критическая ошибка в задаче проверки подписок: {e}", exc_info=True)
        finally:
            db.close()
        time.sleep(60)


def start_bot_polling():
    print("[BOT] Запуск polling...")
    bot.infinity_polling()


def register_handlers(bot):
    from handlers.user_handlers import register_user_handlers
    from handlers.admin_handlers import init_admin_handlers
    from handlers.tariff_handler import register_tariff_handlers

    init_admin_handlers(bot)
    register_user_handlers(bot, payment_service, telegram_channel_service)
    register_tariff_handlers(bot, payment_service)

    # Подхватываем админов из БД на старте
    try:
        db = SessionLocal()
        ids = [a.telegram_id for a in db.query(Admin).all()]
        if ids:
            Config.ADMIN_USER_IDS = ids
            print(f"[CONFIG] Загружены админы: {ids}")
    finally:
        db.close()


if __name__ == '__main__':
    print("[INIT] Ждем готовности базы данных...")
    time.sleep(5)  # Даем время базе данных на инициализацию
    
    print("[INIT] Создаём все таблицы...")
    Base.metadata.create_all(bind=engine)

    print("[INIT] Инициализируем стандартные уведомления...")
    NotificationService.initialize_default_notifications()

    print("[INIT] Регистрируем хендлеры...")
    register_handlers(bot)

    print("[INIT] Запускаем фоновую задачу проверки подписок...")
    subscription_checker_thread = threading.Thread(target=check_expired_subscriptions_task, daemon=True)
    subscription_checker_thread.start()

    print("[INIT] Запускаем сервис отправки уведомлений...")
    notification_sender_service.start()
    
    print("[INIT] Запускаем сервис напоминаний...")
    reminder_service.start_reminder_service()
    
    print("[INIT] Запускаем сервис отслеживания активности...")
    user_activity_service.start()
    
    print("[INIT] Запускаем сервис рассылок марафона...")
    marathon_mailing_service.start()

    # Запускаем polling в отдельном потоке для лучшей логики старта
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()

    print("[INIT] Бот полностью запущен! Ждём работы...")

    # Держим основной поток живым, чтобы контейнер не завершился
    while True:
        time.sleep(10)
