import logging
import threading
import time
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import User, UserNotification, NotificationText
from services.notification_service import NotificationService
from services.notification_sender_service import NotificationSenderService

logger = logging.getLogger(__name__)

class UserActivityService:
    """Сервис для отслеживания активности пользователей и отправки уведомлений"""
    
    def __init__(self, bot):
        self.bot = bot
        self.running = False
        self.thread = None
        self.notification_sender = NotificationSenderService(bot)
    
    def start(self):
        """Запускает сервис отслеживания активности"""
        if self.running:
            logger.warning("Сервис отслеживания активности уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._activity_check_loop, daemon=True)
        self.thread.start()
        logger.info("Сервис отслеживания активности запущен")
    
    def stop(self):
        """Останавливает сервис отслеживания активности"""
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Сервис отслеживания активности остановлен")
    
    def update_user_activity(self, user_telegram_id: int):
        """Обновляет время последней активности пользователя"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
            if user:
                user.last_activity = datetime.utcnow()
                db.commit()
                logger.debug(f"Обновлена активность пользователя {user_telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка обновления активности пользователя {user_telegram_id}: {e}")
            db.rollback()
        finally:
            db.close()
    
    def _activity_check_loop(self):
        """Основной цикл проверки активности пользователей"""
        while self.running:
            try:
                self._check_inactive_users()
                time.sleep(3600)  # Проверяем каждый час
            except Exception as e:
                logger.error(f"Ошибка в цикле проверки активности: {e}")
                time.sleep(3600)
    
    def _check_inactive_users(self):
        """Проверяет неактивных пользователей и планирует уведомления"""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # Проверяем пользователей, неактивных 3 часа
            three_hours_ago = now - timedelta(hours=3)
            inactive_3_hours = db.query(User).filter(
                User.last_activity <= three_hours_ago,
                User.is_active == True
            ).all()
            
            for user in inactive_3_hours:
                self._schedule_inactivity_notification(user.telegram_id, 'inactive_3_hours')
            
            # Проверяем пользователей, неактивных 3 дня
            three_days_ago = now - timedelta(days=3)
            inactive_3_days = db.query(User).filter(
                User.last_activity <= three_days_ago,
                User.is_active == True
            ).all()
            
            for user in inactive_3_days:
                self._schedule_inactivity_notification(user.telegram_id, 'inactive_3_days')
            
            # Проверяем пользователей, неактивных 7 дней
            seven_days_ago = now - timedelta(days=7)
            inactive_7_days = db.query(User).filter(
                User.last_activity <= seven_days_ago,
                User.is_active == True
            ).all()
            
            for user in inactive_7_days:
                self._schedule_inactivity_notification(user.telegram_id, 'inactive_7_days')
            
            logger.info(f"Проверено {len(inactive_3_hours)} пользователей неактивных 3 часа, {len(inactive_3_days)} - 3 дня, {len(inactive_7_days)} - 7 дней")
            
        except Exception as e:
            logger.error(f"Ошибка проверки неактивных пользователей: {e}")
        finally:
            db.close()
    
    def _schedule_inactivity_notification(self, user_telegram_id: int, notification_type: str):
        """Планирует уведомление о неактивности"""
        try:
            # Проверяем, не запланировано ли уже такое уведомление
            db = SessionLocal()
            try:
                existing = db.query(UserNotification).filter(
                    UserNotification.user_id == user_telegram_id,
                    UserNotification.notification_key == notification_type,
                    UserNotification.status == 'scheduled'
                ).first()
                
                if existing:
                    logger.debug(f"Уведомление {notification_type} уже запланировано для пользователя {user_telegram_id}")
                    return
                
                # Получаем случайный вариант текста уведомления
                notification_text = self._get_random_notification_variant(notification_type)
                if not notification_text:
                    logger.warning(f"Текст уведомления {notification_type} не найден")
                    return
                
                # Планируем уведомление
                self.notification_sender.schedule_user_activity_notification(
                    user_telegram_id, 
                    notification_type
                )
                
                logger.info(f"Запланировано уведомление {notification_type} для пользователя {user_telegram_id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка планирования уведомления о неактивности: {e}")
    
    def _get_random_notification_variant(self, notification_key: str):
        """Получает случайный вариант текста уведомления"""
        db = SessionLocal()
        try:
            import random
            
            variants = db.query(NotificationText).filter(
                NotificationText.key == notification_key,
                NotificationText.is_active == True
            ).all()
            
            if variants:
                return random.choice(variants)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения варианта уведомления: {e}")
            return None
        finally:
            db.close()
    
    def get_user_inactivity_stats(self):
        """Получает статистику неактивности пользователей"""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            
            # Пользователи неактивные 1 день
            one_day_ago = now - timedelta(days=1)
            inactive_1_day = db.query(User).filter(
                User.last_activity <= one_day_ago,
                User.is_active == True
            ).count()
            
            # Пользователи неактивные 3 дня
            three_days_ago = now - timedelta(days=3)
            inactive_3_days = db.query(User).filter(
                User.last_activity <= three_days_ago,
                User.is_active == True
            ).count()
            
            # Пользователи неактивные 7 дней
            seven_days_ago = now - timedelta(days=7)
            inactive_7_days = db.query(User).filter(
                User.last_activity <= seven_days_ago,
                User.is_active == True
            ).count()
            
            return {
                'inactive_1_day': inactive_1_day,
                'inactive_3_days': inactive_3_days,
                'inactive_7_days': inactive_7_days
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики неактивности: {e}")
            return {}
        finally:
            db.close()
