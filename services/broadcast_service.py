import logging
from typing import Dict, Any, Optional
from database.connection import SessionLocal
from database.models import User

logger = logging.getLogger(__name__)

class BroadcastService:
    """Сервис для отправки массовых сообщений пользователям (telebot)."""
    def __init__(self, bot):
        self.bot = bot

    def send_direct_broadcast(self, message_data: Dict[str, Any]) -> None:
        text = message_data.get("message", "")
        media_type: Optional[str] = message_data.get("media_type")
        media_file_id: Optional[str] = message_data.get("media_file_id")
        db = SessionLocal()
        try:
            users = db.query(User).filter(User.is_active == True).all()
            for user in users:
                try:
                    if media_type == "photo" and media_file_id:
                        self.bot.send_photo(chat_id=user.telegram_id, photo=media_file_id, caption=text)
                    elif media_type == "video" and media_file_id:
                        self.bot.send_video(chat_id=user.telegram_id, video=media_file_id, caption=text)
                    elif media_type == "document" and media_file_id:
                        self.bot.send_document(chat_id=user.telegram_id, document=media_file_id, caption=text)
                    else:
                        self.bot.send_message(chat_id=user.telegram_id, text=text)
                except Exception as send_err:
                    logger.warning(f"Не удалось отправить сообщение пользователю {user.telegram_id}: {send_err}")
        finally:
            db.close()
    
    def send_subscription_reminder(self, subscription):
        """Отправляет напоминание о скором окончании подписки"""
        try:
            from database.models import Tariff
            from services.user_service import UserService
            
            db = SessionLocal()
            try:
                # Получаем информацию о тарифе
                tariff = db.query(Tariff).filter(Tariff.id == subscription.tariff_id).first()
                
                # Получаем пользователя
                user = UserService.get_user_by_telegram_id(subscription.user_id)
                if not user:
                    logger.warning(f"Пользователь {subscription.user_id} не найден для напоминания")
                    return
                
                # Формируем сообщение
                tariff_name = tariff.name if tariff else "неизвестный тариф"
                end_date = subscription.end_date.strftime('%d.%m.%Y') if subscription.end_date else "неизвестно"
                
                message = (
                    f"⏰ **Напоминание о подписке**\n\n"
                    f"Ваша подписка на тариф **{tariff_name}** скоро закончится!\n"
                    f"📅 Дата окончания: **{end_date}**\n\n"
                    f"Чтобы продолжить пользоваться всеми возможностями, продлите подписку:\n"
                    f"💰 Используйте команду /tariffs"
                )
                
                # Отправляем сообщение
                self.bot.send_message(
                    subscription.user_id,
                    message,
                    parse_mode='Markdown'
                )
                
                # Отмечаем, что напоминание отправлено
                UserService.mark_reminder_sent(subscription.id)
                
                logger.info(f"Напоминание отправлено пользователю {subscription.user_id} о подписке {subscription.id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка отправки напоминания для подписки {subscription.id}: {e}")