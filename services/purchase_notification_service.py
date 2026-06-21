import logging
from datetime import datetime
from config import Config
import telebot

logger = logging.getLogger(__name__)

class PurchaseNotificationService:
    """Сервис для отправки уведомлений о покупках в группу"""
    
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        group_id = Config.TELEGRAM_NOTIFICATIONS_GROUP_ID
        # Преобразуем ID группы в int, если он задан
        if group_id:
            try:
                self.group_id = int(group_id)
            except (ValueError, TypeError):
                self.group_id = group_id  # Оставляем как строку, если не получается преобразовать
        else:
            self.group_id = None
    
    def send_purchase_notification(self, user_id: int, user_info: dict, tariff_name: str, amount: float, payment_id: str = None, promocode: str = None):
        """
        Отправляет уведомление о покупке в группу
        
        Args:
            user_id: Telegram ID пользователя
            user_info: Словарь с информацией о пользователе (username, first_name, last_name)
            tariff_name: Название тарифа
            amount: Сумма покупки
            payment_id: ID платежа (опционально)
            promocode: Использованный промокод (опционально)
        """
        if not self.group_id:
            logger.warning("TELEGRAM_NOTIFICATIONS_GROUP_ID не настроен, уведомление о покупке не отправлено")
            return False
        
        try:
            # Формируем имя пользователя
            username = user_info.get('username')
            first_name = user_info.get('first_name', '')
            last_name = user_info.get('last_name', '')
            
            user_display_name = f"@{username}" if username else f"{first_name} {last_name}".strip() or f"ID: {user_id}"
            
            # Формируем сообщение
            message_text = (
                "🛒 **Новая покупка!**\n\n"
                f"👤 Пользователь: {user_display_name}\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"💰 Тариф: {tariff_name}\n"
                f"💵 Сумма: {amount:.2f} ₽\n"
            )
            
            if payment_id:
                message_text += f"🆔 ID платежа: `{payment_id}`\n"
            
            if promocode:
                message_text += f"🎫 Промокод: `{promocode}`\n"
            
            message_text += f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            
            # Отправляем сообщение в группу
            self.bot.send_message(
                self.group_id,
                message_text,
                parse_mode='Markdown'
            )
            
            logger.info(f"Уведомление о покупке отправлено в группу для пользователя {user_id}")
            return True
            
        except telebot.apihelper.ApiTelegramException as e:
            logger.error(f"Ошибка отправки уведомления о покупке в группу {self.group_id}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при отправке уведомления о покупке: {e}", exc_info=True)
            return False

