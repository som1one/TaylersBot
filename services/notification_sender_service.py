import logging
import threading
import time
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import UserNotification, User
from services.notification_service import NotificationService
from services.user_service import UserService

logger = logging.getLogger(__name__)

class NotificationSenderService:
    """Сервис для отправки запланированных уведомлений"""
    
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.thread = None
    
    def start(self):
        """Запускает сервис отправки уведомлений"""
        if self.running:
            logger.warning("Сервис отправки уведомлений уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._send_notifications_loop, daemon=True)
        self.thread.start()
        logger.info("Сервис отправки уведомлений запущен")
    
    def stop(self):
        """Останавливает сервис отправки уведомлений"""
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Сервис отправки уведомлений остановлен")
    
    def _send_notifications_loop(self):
        """Основной цикл отправки уведомлений"""
        while self.running:
            try:
                self._process_pending_notifications()
                time.sleep(300)  # Проверяем каждые 5 минут
            except Exception as e:
                logger.error(f"Ошибка в цикле отправки уведомлений: {e}")
                time.sleep(60)
    
    def _process_pending_notifications(self):
        """Обрабатывает все готовые к отправке уведомления"""
        pending_notifications = NotificationService.get_pending_notifications()
        
        for notification in pending_notifications:
            try:
                self._send_notification(notification)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления {notification.id}: {e}")
                # Помечаем как неудачное
                self._mark_notification_failed(notification.id)
    
    def _send_notification(self, notification):
        """Отправляет одно уведомление"""
        try:
            # Получаем случайный вариант текста уведомления
            notification_text = NotificationService.get_random_notification_variant(notification.notification_key)
            if not notification_text:
                logger.warning(f"Текст уведомления {notification.notification_key} не найден")
                self._mark_notification_failed(notification.id)
                return
            
            # Получаем пользователя
            user = UserService.get_user_by_telegram_id(notification.user_id)
            if not user:
                logger.warning(f"Пользователь {notification.user_id} не найден")
                self._mark_notification_failed(notification.id)
                return
            
            # Отправляем сообщение
            message_text = f"🔔 **{notification_text.title}**\n\n{notification_text.text}"
            
            self.bot.send_message(
                notification.user_id,
                message_text,
                parse_mode='Markdown'
            )
            
            # Помечаем как отправленное
            NotificationService.mark_notification_sent(notification.id)
            logger.info(f"Уведомление {notification.notification_key} отправлено пользователю {notification.user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления {notification.id}: {e}")
            self._mark_notification_failed(notification.id)
    
    def _mark_notification_failed(self, notification_id):
        """Помечает уведомление как неудачное"""
        db = SessionLocal()
        try:
            notification = db.query(UserNotification).filter(
                UserNotification.id == notification_id
            ).first()
            
            if notification:
                notification.status = 'failed'
                db.commit()
                logger.info(f"Уведомление {notification_id} помечено как неудачное")
        except Exception as e:
            logger.error(f"Ошибка отметки уведомления как неудачного: {e}")
            db.rollback()
        finally:
            db.close()
    
    def schedule_user_activity_notification(self, user_telegram_id: int, activity_type: str):
        """Планирует уведомление на основе активности пользователя"""
        try:
            if activity_type == 'visited_no_action':
                # Пользователь зашел, но не выполнил действий
                NotificationService.schedule_notification(
                    user_telegram_id, 
                    'user_visited_no_action', 
                    delay_hours=3
                )
                
            elif activity_type == 'payment_not_completed':
                # Пользователь начал оплату, но не завершил
                NotificationService.schedule_notification(
                    user_telegram_id, 
                    'payment_not_completed', 
                    delay_hours=1
                )
                
            elif activity_type == 'inactive_3_days':
                # Пользователь неактивен 3 дня
                NotificationService.schedule_notification(
                    user_telegram_id, 
                    'inactive_3_days', 
                    delay_hours=0
                )
                
            elif activity_type == 'inactive_7_days':
                # Пользователь неактивен 7 дней
                NotificationService.schedule_notification(
                    user_telegram_id, 
                    'inactive_7_days', 
                    delay_hours=0
                )
                
        except Exception as e:
            logger.error(f"Ошибка планирования уведомления для пользователя {user_telegram_id}: {e}")
    
    def cancel_user_notifications(self, user_telegram_id: int, notification_key: str = None):
        """Отменяет уведомления пользователя"""
        try:
            if notification_key:
                # Отменяем конкретное уведомление
                NotificationService.cancel_notification(user_telegram_id, notification_key)
            else:
                # Отменяем все уведомления пользователя
                db = SessionLocal()
                try:
                    notifications = db.query(UserNotification).filter(
                        UserNotification.user_id == user_telegram_id,
                        UserNotification.status == 'scheduled'
                    ).all()
                    
                    for notification in notifications:
                        notification.status = 'cancelled'
                    
                    db.commit()
                    logger.info(f"Отменено {len(notifications)} уведомлений для пользователя {user_telegram_id}")
                finally:
                    db.close()
                    
        except Exception as e:
            logger.error(f"Ошибка отмены уведомлений для пользователя {user_telegram_id}: {e}")
