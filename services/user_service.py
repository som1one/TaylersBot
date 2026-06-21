from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.models import User, Subscription, Tariff
from database.connection import SessionLocal

class UserService:
    @staticmethod
    def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None, last_name: str = None, referred_by: int = None):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            
            if not user:
                user = User(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    referred_by=referred_by  # Сохраняем referred_by при создании нового пользователя
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                # Обновляем данные существующего пользователя
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                if user.referred_by is None and referred_by is not None: # Записываем referred_by только если его еще нет
                    user.referred_by = referred_by
                user.updated_at = datetime.utcnow()
                db.commit()
                db.refresh(user)
            
            return user
        finally:
            db.close()
    
    @staticmethod
    def get_user_by_telegram_id(telegram_id: int):
        db = SessionLocal()
        try:
            return db.query(User).filter(User.telegram_id == telegram_id).first()
        finally:
            db.close()
    
    @staticmethod
    def get_active_subscription(user_id: int):
        db = SessionLocal()
        try:
            return db.query(Subscription).filter(
                Subscription.user_id == user_id,
                Subscription.is_active == True,
                Subscription.end_date > datetime.utcnow()
            ).first()
        finally:
            db.close()
    
    @staticmethod
    def get_subscriptions_ending_soon(days: int = 3):
        db = SessionLocal()
        try:
            end_date = datetime.utcnow() + timedelta(days=days)
            return db.query(Subscription).filter(
                Subscription.is_active == True,
                Subscription.end_date <= end_date,
                Subscription.reminder_sent == False
            ).all()
        finally:
            db.close()
    
    @staticmethod
    def mark_reminder_sent(subscription_id: int):
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if subscription:
                subscription.reminder_sent = True
                db.commit()
        finally:
            db.close()
    
    @staticmethod
    def get_all_users():
        db = SessionLocal()
        try:
            return db.query(User).filter(User.is_active == True).all()
        finally:
            db.close()
    
    @staticmethod
    def get_users_count():
        db = SessionLocal()
        try:
            return db.query(User).filter(User.is_active == True).count()
        finally:
            db.close() 

    @staticmethod
    def get_expired_active_subscriptions():
        db = SessionLocal()
        try:
            return db.query(Subscription).filter(
                Subscription.is_active == True,
                Subscription.end_date <= datetime.utcnow() # Истекшие подписки
            ).all()
        finally:
            db.close()

    @staticmethod
    def mark_subscription_inactive(subscription_id: int):
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if subscription:
                subscription.is_active = False
                db.commit()
                return True
            return False
        finally:
            db.close() 