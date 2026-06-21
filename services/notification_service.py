import logging
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import NotificationText, UserNotification, User
from services.user_service import UserService

logger = logging.getLogger(__name__)

class NotificationService:
    """Сервис для управления уведомлениями пользователей"""
    
    @staticmethod
    def get_notification_text(key: str, variant: str = "default") -> NotificationText:
        """Получает текст уведомления по ключу и варианту"""
        db = SessionLocal()
        try:
            return db.query(NotificationText).filter(
                NotificationText.key == key,
                NotificationText.variant == variant,
                NotificationText.is_active == True
            ).first()
        finally:
            db.close()
    
    @staticmethod
    def get_random_notification_variant(key: str) -> NotificationText:
        """Получает случайный вариант текста уведомления"""
        db = SessionLocal()
        try:
            import random
            
            variants = db.query(NotificationText).filter(
                NotificationText.key == key,
                NotificationText.is_active == True
            ).all()
            
            if variants:
                return random.choice(variants)
            return None
            
        finally:
            db.close()
    
    @staticmethod
    def schedule_notification(user_telegram_id: int, notification_key: str, delay_hours: int = 0):
        """Планирует уведомление для пользователя"""
        db = SessionLocal()
        try:
            # Проверяем, есть ли уже запланированное уведомление
            existing = db.query(UserNotification).filter(
                UserNotification.user_id == user_telegram_id,
                UserNotification.notification_key == notification_key,
                UserNotification.status == 'scheduled'
            ).first()
            
            if existing:
                logger.info(f"Уведомление {notification_key} уже запланировано для пользователя {user_telegram_id}")
                return existing
            
            # Получаем текст уведомления
            notification_text = NotificationService.get_notification_text(notification_key)
            if not notification_text:
                logger.warning(f"Текст уведомления {notification_key} не найден")
                return None
            
            # Рассчитываем время отправки
            scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)
            
            # Создаем запись о запланированном уведомлении
            user_notification = UserNotification(
                user_id=user_telegram_id,
                notification_key=notification_key,
                scheduled_at=scheduled_at,
                status='scheduled'
            )
            
            db.add(user_notification)
            db.commit()
            
            logger.info(f"Запланировано уведомление {notification_key} для пользователя {user_telegram_id} на {scheduled_at}")
            return user_notification
            
        except Exception as e:
            logger.error(f"Ошибка планирования уведомления: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    @staticmethod
    def cancel_notification(user_telegram_id: int, notification_key: str):
        """Отменяет запланированное уведомление"""
        db = SessionLocal()
        try:
            notifications = db.query(UserNotification).filter(
                UserNotification.user_id == user_telegram_id,
                UserNotification.notification_key == notification_key,
                UserNotification.status == 'scheduled'
            ).all()
            
            for notification in notifications:
                notification.status = 'cancelled'
            
            db.commit()
            logger.info(f"Отменено {len(notifications)} уведомлений {notification_key} для пользователя {user_telegram_id}")
            return len(notifications)
            
        except Exception as e:
            logger.error(f"Ошибка отмены уведомления: {e}")
            db.rollback()
            return 0
        finally:
            db.close()
    
    @staticmethod
    def get_pending_notifications():
        """Получает все уведомления, готовые к отправке"""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            return db.query(UserNotification).filter(
                UserNotification.status == 'scheduled',
                UserNotification.scheduled_at <= now
            ).all()
        finally:
            db.close()
    
    @staticmethod
    def mark_notification_sent(notification_id: int):
        """Отмечает уведомление как отправленное"""
        db = SessionLocal()
        try:
            notification = db.query(UserNotification).filter(
                UserNotification.id == notification_id
            ).first()
            
            if notification:
                notification.status = 'sent'
                notification.sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Уведомление {notification_id} отмечено как отправленное")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка отметки уведомления как отправленного: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_all_notification_texts():
        """Получает все тексты уведомлений"""
        db = SessionLocal()
        try:
            return db.query(NotificationText).order_by(NotificationText.key).all()
        finally:
            db.close()
    
    @staticmethod
    def create_or_update_notification_text(key: str, title: str, text: str, variant: str = "default", trigger_condition: str = None, delay_hours: int = 0, priority: int = 1):
        """Создает или обновляет текст уведомления"""
        db = SessionLocal()
        try:
            notification_text = db.query(NotificationText).filter(
                NotificationText.key == key,
                NotificationText.variant == variant
            ).first()
            
            if notification_text:
                # Обновляем существующий
                notification_text.title = title
                notification_text.text = text
                notification_text.trigger_condition = trigger_condition
                notification_text.delay_hours = delay_hours
                notification_text.priority = priority
                notification_text.updated_at = datetime.utcnow()
            else:
                # Создаем новый
                notification_text = NotificationText(
                    key=key,
                    variant=variant,
                    title=title,
                    text=text,
                    trigger_condition=trigger_condition,
                    delay_hours=delay_hours,
                    priority=priority
                )
                db.add(notification_text)
            
            db.commit()
            logger.info(f"Сохранен текст уведомления {key} вариант {variant}")
            return notification_text
            
        except Exception as e:
            logger.error(f"Ошибка сохранения текста уведомления: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    @staticmethod
    def delete_notification_text(key: str, variant: str = None):
        """Удаляет текст уведомления"""
        db = SessionLocal()
        try:
            if variant:
                # Удаляем конкретный вариант
                notification_text = db.query(NotificationText).filter(
                    NotificationText.key == key,
                    NotificationText.variant == variant
                ).first()
                
                if notification_text:
                    db.delete(notification_text)
                    db.commit()
                    logger.info(f"Удален текст уведомления {key} вариант {variant}")
                    return True
            else:
                # Удаляем все варианты с данным ключом
                notification_texts = db.query(NotificationText).filter(
                    NotificationText.key == key
                ).all()
                
                for notification_text in notification_texts:
                    db.delete(notification_text)
                
                db.commit()
                logger.info(f"Удалены все варианты текста уведомления {key}")
                return len(notification_texts) > 0
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка удаления текста уведомления: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def initialize_default_notifications():
        """Инициализирует стандартные уведомления"""
        # База пустая - никаких стандартных уведомлений
        logger.info("База уведомлений пустая - стандартные уведомления не созданы")
