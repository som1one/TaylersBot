import logging
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import User, MarathonMaterial, MarathonPost, UserMarathonStatus, Subscription

logger = logging.getLogger(__name__)

class MarathonService:
    """Сервис для управления марафоном и воронкой продаж"""
    
    @staticmethod
    def get_or_create_user_status(user_id: int):
        """Получает или создает статус пользователя в марафоне"""
        db = SessionLocal()
        try:
            status = db.query(UserMarathonStatus).filter_by(user_id=user_id).first()
            if not status:
                status = UserMarathonStatus(
                    user_id=user_id,
                    status='new',
                    current_week=0,
                    posts_sent_in_cycle=0
                )
                db.add(status)
                db.commit()
                db.refresh(status)
            return status
        finally:
            db.close()
    
    @staticmethod
    def update_user_status(user_id: int, status: str = None, **kwargs):
        """Обновляет статус пользователя"""
        db = SessionLocal()
        try:
            user_status = db.query(UserMarathonStatus).filter_by(user_id=user_id).first()
            if not user_status:
                user_status = MarathonService.get_or_create_user_status(user_id)
                db = SessionLocal()  # Новая сессия после закрытия
                user_status = db.query(UserMarathonStatus).filter_by(user_id=user_id).first()
            
            if status:
                user_status.status = status
            for key, value in kwargs.items():
                if hasattr(user_status, key):
                    setattr(user_status, key, value)
            
            user_status.updated_at = datetime.utcnow()
            db.commit()
            return user_status
        except Exception as e:
            logger.error(f"Ошибка обновления статуса пользователя {user_id}: {e}", exc_info=True)
            db.rollback()
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_training_video(category: str = None):
        """Получает обучающее видео"""
        db = SessionLocal()
        try:
            query = db.query(MarathonMaterial).filter_by(
                material_type='training_video',
                is_active=True
            )
            if category:
                query = query.filter_by(category=category)
            
            material = query.order_by(MarathonMaterial.order_index).first()
            return material
        finally:
            db.close()
    
    @staticmethod
    def get_marathon_intro_video():
        """Получает видео обращение при вступлении в марафон"""
        db = SessionLocal()
        try:
            material = db.query(MarathonMaterial).filter_by(
                material_type='marathon_intro_video',
                is_active=True
            ).order_by(MarathonMaterial.order_index).first()
            return material
        finally:
            db.close()
    
    @staticmethod
    def get_category_message(category: str = None):
        """Получает сообщение для категории при /start"""
        db = SessionLocal()
        try:
            query = db.query(MarathonMaterial).filter_by(
                material_type='category_message',
                is_active=True
            )
            if category:
                query = query.filter_by(category=category)
            
            material = query.order_by(MarathonMaterial.order_index).first()
            return material
        finally:
            db.close()
    
    @staticmethod
    def get_post_for_cycle(week: int, post_type: str, day_number: int = None):
        """Получает пост для цикла"""
        db = SessionLocal()
        try:
            query = db.query(MarathonPost).filter_by(
                post_type=post_type,
                is_active=True
            )
            
            if day_number:
                query = query.filter_by(day_number=day_number)
            
            post = query.order_by(MarathonPost.day_number).first()
            return post
        finally:
            db.close()
    
    @staticmethod
    def should_open_subscription(user_id: int):
        """Проверяет, нужно ли открыть подписку (каждые 7 дней)"""
        db = SessionLocal()
        try:
            user_status = db.query(UserMarathonStatus).filter_by(user_id=user_id).first()
            if not user_status:
                return True  # Новый пользователь - открываем
            
            # Проверяем, прошло ли 7 дней с последнего открытия
            if not user_status.subscription_opened_at:
                return True
            
            days_since_opening = (datetime.utcnow() - user_status.subscription_opened_at).days
            return days_since_opening >= 7
        finally:
            db.close()
    
    @staticmethod
    def user_has_active_subscription(user_id: int):
        """Проверяет, есть ли у пользователя активная подписка"""
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(
                Subscription.user_id == user_id,
                Subscription.is_active == True,
                Subscription.end_date > datetime.utcnow()
            ).first()
            return subscription is not None
        finally:
            db.close()
    
    @staticmethod
    def can_user_join_marathon(user_id: int):
        """Проверяет, может ли пользователь вступить в марафон (не вышел ли недавно)"""
        db = SessionLocal()
        try:
            user_status = db.query(UserMarathonStatus).filter_by(user_id=user_id).first()
            if not user_status or not user_status.left_marathon_at:
                return True
            
            # Проверяем, прошло ли 6 месяцев
            months_since_leave = (datetime.utcnow() - user_status.left_marathon_at).days / 30
            return months_since_leave >= 6
        finally:
            db.close()
    
    @staticmethod
    def mark_user_left_marathon(user_id: int):
        """Отмечает, что пользователь вышел из марафона"""
        MarathonService.update_user_status(
            user_id,
            status='left',
            left_marathon_at=datetime.utcnow()
        )
    
    @staticmethod
    def get_users_for_mailing(post_type: str = 'warmup'):
        """Получает список пользователей для рассылки постов"""
        db = SessionLocal()
        try:
            # Получаем пользователей, которые не купили подписку и не должны получать рассылки
            users_statuses = db.query(UserMarathonStatus).filter(
                UserMarathonStatus.status.in_(['first_week', 'second_week', 'hard_posts', 'free_call_offered'])
            ).all()
            
            result = []
            for status in users_statuses:
                # Проверяем, что у пользователя нет активной подписки
                if MarathonService.user_has_active_subscription(status.user_id):
                    continue
                
                # Проверяем тип поста
                if post_type == 'warmup' and status.status in ['first_week', 'second_week']:
                    result.append(status.user_id)
                elif post_type == 'hard' and status.status == 'hard_posts':
                    result.append(status.user_id)
                
            return result
        finally:
            db.close()

