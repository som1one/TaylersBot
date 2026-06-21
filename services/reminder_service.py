import logging
import threading
import time
from datetime import datetime, timedelta
from services.user_service import UserService
from services.broadcast_service import BroadcastService

logger = logging.getLogger(__name__)

class ReminderService:
    def __init__(self, broadcast_service: BroadcastService):
        self.broadcast_service = broadcast_service
        self.is_running = False
        self.thread = None
    
    def start_reminder_service(self):
        """Запуск сервиса напоминаний"""
        if self.is_running:
            logger.warning("Сервис напоминаний уже запущен")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._reminder_loop, daemon=True)
        self.thread.start()
        logger.info("Сервис напоминаний запущен")
    
    def stop_reminder_service(self):
        """Остановка сервиса напоминаний"""
        self.is_running = False
        if self.thread:
            self.thread.join()
        logger.info("Сервис напоминаний остановлен")
    
    def _reminder_loop(self):
        """Основной цикл проверки напоминаний"""
        while self.is_running:
            try:
                self.check_and_send_reminders()
                time.sleep(6 * 60 * 60)  # Проверяем каждые 6 часов
            except Exception as e:
                logger.error(f"Ошибка в сервисе напоминаний: {e}")
                time.sleep(60)
    
    def check_and_send_reminders(self):
        """Проверка и отправка напоминаний"""
        try:
            subscriptions = UserService.get_subscriptions_ending_soon(days=3)
            
            if not subscriptions:
                logger.info("Нет подписок, требующих напоминаний")
                return
            
            logger.info(f"Найдено {len(subscriptions)} подписок для напоминаний")
            
            for subscription in subscriptions:
                try:
                    self.broadcast_service.send_subscription_reminder(subscription)
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания для подписки {subscription.id}: {e}")
            
            logger.info(f"Напоминания отправлены для {len(subscriptions)} подписок")
            
        except Exception as e:
            logger.error(f"Ошибка проверки напоминаний: {e}")
    
    def send_immediate_reminder(self, subscription_id: int):
        """Немедленная отправка напоминания"""
        try:
            from database.models import Subscription
            from database.connection import SessionLocal
            
            db = SessionLocal()
            try:
                subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
                if subscription:
                    self.broadcast_service.send_subscription_reminder(subscription)
                    logger.info(f"Немедленное напоминание отправлено для подписки {subscription_id}")
                else:
                    logger.warning(f"Подписка {subscription_id} не найдена")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка отправки немедленного напоминания: {e}")
    
    def test_reminder(self, user_id: int):
        """Тестовая отправка напоминания"""
        try:
            from database.models import Subscription, Tariff
            from database.connection import SessionLocal
            
            db = SessionLocal()
            try:
                # Создаем тестовую подписку
                test_tariff = Tariff(
                    name="Тестовый тариф",
                    price=100.0,
                    duration_days=30
                )
                db.add(test_tariff)
                db.flush()
                
                test_subscription = Subscription(
                    user_id=user_id,
                    tariff_id=test_tariff.id,
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=1),
                    is_active=True
                )
                db.add(test_subscription)
                db.commit()
                self.broadcast_service.send_subscription_reminder(test_subscription)
                
                logger.info(f"Тестовое напоминание отправлено пользователю {user_id}")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка тестовой отправки напоминания: {e}") 