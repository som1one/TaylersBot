from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, BigInteger, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    total_spent = Column(Float, default=0.0)
    is_ambassador = Column(Boolean, default=False)
    ambassador_code = Column(String, unique=True, nullable=True)
    referred_by = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=True)
    last_activity = Column(DateTime, default=datetime.utcnow)  # Время последней активности
    
    # Отношения
    subscriptions = relationship("Subscription", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    referrals = relationship("User", backref="referrer", remote_side=[telegram_id])

class Tariff(Base):
    __tablename__ = "tariffs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration_days = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    is_main = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    subscriptions = relationship("Subscription", back_populates="tariff")

class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = {"schema": "public"} 
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    reminder_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User", back_populates="subscriptions")
    tariff = relationship("Tariff", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "public"}  # <-- добавляем схему

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("public.subscriptions.id"), nullable=True)  # <-- указываем схему
    yookassa_payment_id = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Отношения
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")


class PromoCode(Base):
    __tablename__ = "promocodes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False)
    discount_percent = Column(Integer, nullable=True)  # 0-100
    is_free = Column(Boolean, default=False)
    duration_days = Column(Integer, nullable=True)  # сколько дней действует промо
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    usage_limit = Column(Integer, nullable=True)  # сколько раз можно использовать
    usage_count = Column(Integer, default=0)  # сколько раз уже использовано
    created_at = Column(DateTime, default=datetime.utcnow)

class Admin(Base):
    __tablename__ = "admins"
    
    telegram_id = Column(BigInteger, primary_key=True, unique=True, nullable=False)
    username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class Ambassador(Base):
    __tablename__ = "ambassadors"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    # Статистика амбассадора
    total_referrals = Column(Integer, default=0)  # Общее количество рефералов
    active_referrals = Column(Integer, default=0)  # Активные рефералы
    total_earnings = Column(Float, default=0.0)  # Общий заработок
    pending_payout = Column(Float, default=0.0)  # Ожидающая выплата

class AmbassadorStats(Base):
    __tablename__ = "ambassador_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    referral_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    action_type = Column(String, nullable=False)  # 'click', 'subscription', 'payment'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User", foreign_keys=[user_id])
    referral = relationship("User", foreign_keys=[referral_id])

class Broadcast(Base):
    __tablename__ = "broadcasts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    media_type = Column(String(20), nullable=True)  # photo, video, document
    media_file_id = Column(String(200), nullable=True)
    status = Column(String(20), default='draft')  # draft, sent, scheduled
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    creator = relationship("User")

class BroadcastLog(Base):
    __tablename__ = "broadcast_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    broadcast_id = Column(Integer, ForeignKey("broadcasts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False)  # sent, failed, blocked
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    broadcast = relationship("Broadcast")
    user = relationship("User")

class PaymentLinkUsage(Base):
    __tablename__ = "payment_link_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    payment_id = Column(String, nullable=False)  # ID платежа в ЮKassa
    link_used = Column(Boolean, default=False)  # Использована ли ссылка
    used_at = Column(DateTime, nullable=True)  # Когда была использована
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User")

class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    error_type = Column(String, nullable=False)  # Тип ошибки (ApiTelegramException, Exception и т.д.)
    error_message = Column(Text, nullable=False)  # Сообщение об ошибке
    error_traceback = Column(Text, nullable=True)  # Полный трейсбек
    function_name = Column(String, nullable=True)  # Имя функции, где произошла ошибка
    user_id = Column(BigInteger, nullable=True)  # ID пользователя, если применимо
    chat_id = Column(BigInteger, nullable=True)  # ID чата, если применимо
    severity = Column(String, default='error')  # 'error', 'warning', 'critical'
    is_resolved = Column(Boolean, default=False)  # Решена ли ошибка
    created_at = Column(DateTime, default=datetime.utcnow)

class NotificationText(Base):
    __tablename__ = "notification_texts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False)  # Ключ для идентификации типа уведомления
    variant = Column(String, nullable=False)  # Вариант текста
    title = Column(String, nullable=False)  # Заголовок уведомления
    text = Column(Text, nullable=False)  # Текст уведомления
    is_active = Column(Boolean, default=True)  # Активно ли уведомление
    trigger_condition = Column(String, nullable=True)  # Условие срабатывания (например, "3_days_inactive")
    delay_hours = Column(Integer, default=0)  # Задержка в часах перед отправкой
    priority = Column(Integer, default=1)  # Приоритет (чем выше, тем важнее)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    # Уникальный индекс для комбинации key + variant
    __table_args__ = (
        UniqueConstraint('key', 'variant', name='unique_notification_key_variant'),
    )

class UserNotification(Base):
    __tablename__ = "user_notifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    notification_key = Column(String, nullable=False)  # Ключ уведомления
    sent_at = Column(DateTime, nullable=True)  # Когда было отправлено
    scheduled_at = Column(DateTime, nullable=True)  # Когда запланировано к отправке
    status = Column(String, default='scheduled')  # scheduled, sent, failed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    user = relationship("User")

class MarathonMaterial(Base):
    """Материалы для марафона (обучалки, видео обращения и т.д.)"""
    __tablename__ = "marathon_materials"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    material_type = Column(String, nullable=False)  # 'training_video', 'marathon_intro_video', 'category_message'
    title = Column(String, nullable=False)  # Название материала
    description = Column(Text, nullable=True)  # Описание
    file_id = Column(String, nullable=True)  # Telegram file_id для видео/фото
    file_type = Column(String, nullable=True)  # 'video', 'photo', 'document'
    text_content = Column(Text, nullable=True)  # Текстовый контент (для сообщений)
    category = Column(String, nullable=True)  # Категория пользователей (если нужна)
    is_active = Column(Boolean, default=True)
    order_index = Column(Integer, default=0)  # Порядок отображения
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MarathonPost(Base):
    """Посты для рассылок в марафоне"""
    __tablename__ = "marathon_posts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_type = Column(String, nullable=False)  # 'warmup', 'hard', 'regular' - тип поста
    day_number = Column(Integer, nullable=False)  # Номер дня (1-7 для недельного цикла)
    title = Column(String, nullable=True)
    text_content = Column(Text, nullable=False)  # Текст поста
    file_id = Column(String, nullable=True)  # Telegram file_id для медиа
    file_type = Column(String, nullable=True)  # 'video', 'photo', 'document'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserMarathonStatus(Base):
    """Отслеживание статуса пользователя в воронке марафона"""
    __tablename__ = "user_marathon_status"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, unique=True)
    status = Column(String, nullable=False, default='new')  # 'new', 'first_week', 'second_week', 'free_call_offered', 'hard_posts', 'subscribed'
    current_week = Column(Integer, default=0)  # Текущая неделя цикла
    last_post_sent_at = Column(DateTime, nullable=True)  # Когда был отправлен последний пост
    last_cycle_start = Column(DateTime, nullable=True)  # Когда начался текущий 7-дневный цикл
    posts_sent_in_cycle = Column(Integer, default=0)  # Сколько постов отправлено в текущем цикле
    free_call_offered = Column(Boolean, default=False)  # Предложен ли бесплатный созвон
    free_call_scheduled = Column(Boolean, default=False)  # Запланирован ли созвон
    subscription_opened_at = Column(DateTime, nullable=True)  # Когда открывалась подписка в последний раз
    left_marathon_at = Column(DateTime, nullable=True)  # Когда вышел из марафона (для блокировки на 6 месяцев)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Отношения
    user = relationship("User")