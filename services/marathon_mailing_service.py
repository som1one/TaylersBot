import logging
import threading
import time
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import UserMarathonStatus, Subscription, MarathonPost
from services.marathon_service import MarathonService
import telebot

logger = logging.getLogger(__name__)

class MarathonMailingService:
    """Сервис для рассылки постов марафона каждые 7 дней"""
    
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self.running = False
        self.thread = None
    
    def start(self):
        """Запускает сервис рассылок"""
        if self.running:
            logger.warning("Сервис рассылок уже запущен")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._mailing_loop, daemon=True)
        self.thread.start()
        logger.info("Сервис рассылок марафона запущен")
    
    def stop(self):
        """Останавливает сервис рассылок"""
        self.running = False
        logger.info("Сервис рассылок марафона остановлен")
    
    def _mailing_loop(self):
        """Основной цикл рассылки"""
        while self.running:
            try:
                self._process_cycle()
                # Проверяем каждые 10 минут для более быстрой реакции
                time.sleep(600)
            except Exception as e:
                logger.error(f"Ошибка в цикле рассылки: {e}", exc_info=True)
                time.sleep(300)  # 5 минут при ошибке
    
    def _process_cycle(self):
        """Обрабатывает один цикл рассылки"""
        logger.info("[_process_cycle] Начало обработки цикла рассылки")
        db = SessionLocal()
        try:
            # Получаем всех пользователей, которым нужно отправить посты
            user_statuses = db.query(UserMarathonStatus).filter(
                UserMarathonStatus.status.in_(['first_week', 'second_week', 'hard_posts', 'free_call_offered'])
            ).all()
            
            logger.info(f"[_process_cycle] Найдено {len(user_statuses)} пользователей для обработки")
            
            if len(user_statuses) == 0:
                logger.debug("[_process_cycle] Нет пользователей для обработки")
            
            now = datetime.utcnow()
            
            for status in user_statuses:
                try:
                    logger.debug(f"[_process_cycle] Обработка пользователя {status.user_id}, статус: {status.status}")
                    
                    # Проверяем, не купил ли пользователь
                    subscription = db.query(Subscription).filter(
                        Subscription.user_id == status.user_id,
                        Subscription.is_active == True,
                        Subscription.end_date > datetime.utcnow()
                    ).first()
                    
                    if subscription:
                        # Пользователь купил - обновляем статус и прекращаем рассылки
                        logger.info(f"[_process_cycle] Пользователь {status.user_id} купил подписку, прекращаем рассылки")
                        status.status = 'subscribed'
                        status.updated_at = now
                        db.commit()
                        continue
                    
                    # Проверяем начало нового 7-дневного цикла
                    if not status.last_cycle_start:
                        status.last_cycle_start = now
                        status.posts_sent_in_cycle = 0
                        db.commit()
                    
                    days_in_cycle = (now - status.last_cycle_start).days
                    
                    # Если прошло 7 дней, начинаем новый цикл
                    if days_in_cycle >= 7:
                        self._start_new_cycle(status, db)
                        continue
                    
                    # Проверяем, нужно ли отправить пост (раз в день, минимум 24 часа между постами)
                    if status.last_post_sent_at:
                        hours_since_last_post = (now - status.last_post_sent_at).total_seconds() / 3600
                        if hours_since_last_post < 24:  # Отправляем раз в день (24 часа)
                            continue
                    
                    # Определяем тип поста и день
                    day_number = status.posts_sent_in_cycle + 1
                    
                    if status.status == 'first_week':
                        post_type = 'warmup'
                    elif status.status == 'second_week':
                        post_type = 'warmup'
                    elif status.status == 'free_call_offered':
                        post_type = 'warmup'  # Продолжаем догревочные посты
                    elif status.status == 'hard_posts':
                        post_type = 'hard'
                    else:
                        post_type = 'warmup'
                        logger.warning(f"Неизвестный статус {status.status} для пользователя {status.user_id}, используется warmup")
                    
                    logger.debug(f"[_process_cycle] Пользователь {status.user_id}, день {day_number}, тип поста: {post_type}")
                    
                    # Получаем пост
                    query = db.query(MarathonPost).filter_by(
                        post_type=post_type,
                        is_active=True
                    )
                    if day_number:
                        query = query.filter_by(day_number=day_number)
                    post = query.order_by(MarathonPost.day_number).first()
                    
                    if post:
                        try:
                            self._send_post(status.user_id, post)
                            
                            # Обновляем статус
                            status.last_post_sent_at = now
                            status.posts_sent_in_cycle += 1
                            status.updated_at = now
                            db.commit()
                            logger.info(f"Пост {post.id} отправлен пользователю {status.user_id}, день {day_number}, тип: {post_type}")
                        except Exception as send_error:
                            logger.error(f"Ошибка отправки поста пользователю {status.user_id}: {send_error}", exc_info=True)
                    else:
                        logger.warning(f"Пост не найден для пользователя {status.user_id}, день {day_number}, тип {post_type}")
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки пользователя {status.user_id}: {e}", exc_info=True)
                    
        finally:
            db.close()
    
    def _start_new_cycle(self, user_status: UserMarathonStatus, db_session=None):
        """Начинает новый 7-дневный цикл"""
        close_db = False
        if db_session is None:
            db_session = SessionLocal()
            close_db = True
        
        try:
            now = datetime.utcnow()
            
            # Открываем подписку
            user_status.subscription_opened_at = now
            user_status.last_cycle_start = now
            user_status.posts_sent_in_cycle = 0
            user_status.last_post_sent_at = None
            
            # Обновляем статус в зависимости от текущего статуса
            old_status = user_status.status
            if user_status.status == 'new':
                user_status.status = 'first_week'
                user_status.current_week = 1
            elif user_status.status == 'first_week':
                # Переходим ко второй неделе
                user_status.status = 'second_week'
                user_status.current_week = 2
            elif user_status.status == 'second_week':
                # После второй недели предлагаем бесплатный созвон
                if not user_status.free_call_offered:
                    user_status.status = 'free_call_offered'
                    user_status.free_call_offered = True
                    # Отправляем сообщение о бесплатном созвоне
                    try:
                        self._send_free_call_offer(user_status.user_id)
                    except Exception as e:
                        logger.error(f"Ошибка отправки предложения о созвоне: {e}")
                else:
                    user_status.status = 'hard_posts'
            
            user_status.updated_at = now
            db_session.commit()
            logger.info(f"Начат новый цикл для пользователя {user_status.user_id}, статус изменен: {old_status} -> {user_status.status}")
        except Exception as e:
            logger.error(f"Ошибка начала нового цикла для пользователя {user_status.user_id}: {e}", exc_info=True)
            db_session.rollback()
        finally:
            if close_db:
                db_session.close()
    
    def _send_post(self, user_id: int, post):
        """Отправляет пост пользователю"""
        try:
            if post.file_id and post.file_type == 'video':
                self.bot.send_video(user_id, post.file_id, caption=post.text_content)
            elif post.file_id and post.file_type == 'photo':
                self.bot.send_photo(user_id, post.file_id, caption=post.text_content)
            elif post.file_id and post.file_type == 'document':
                self.bot.send_document(user_id, post.file_id, caption=post.text_content)
            else:
                self.bot.send_message(user_id, post.text_content)
            
            logger.info(f"Пост {post.id} отправлен пользователю {user_id}")
        except telebot.apihelper.ApiTelegramException as e:
            # Ошибки Telegram API (пользователь заблокировал бота, неверный chat_id и т.д.)
            error_msg = str(e).lower()
            if "chat not found" in error_msg or "user is deactivated" in error_msg:
                logger.warning(f"Пользователь {user_id} недоступен для отправки поста {post.id}: {e}")
            else:
                logger.error(f"Telegram API ошибка при отправке поста {post.id} пользователю {user_id}: {e}")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка отправки поста {post.id} пользователю {user_id}: {e}", exc_info=True)
    
    def _send_free_call_offer(self, user_id: int):
        """Отправляет предложение о бесплатном созвоне"""
        try:
            message = (
                "🎁 Специальное предложение!\n\n"
                "Вы получаете возможность записаться на бесплатный 15-минутный созвон со мной, "
                "где мы решим ваши проблемы и обсудим, подходит ли вам марафон.\n\n"
                "Это ваш последний шанс перед переходом на жесткие посты."
            )
            self.bot.send_message(user_id, message)
            logger.info(f"Предложение о бесплатном созвоне отправлено пользователю {user_id}")
        except telebot.apihelper.ApiTelegramException as e:
            error_msg = str(e).lower()
            if "chat not found" in error_msg or "user is deactivated" in error_msg:
                logger.warning(f"Пользователь {user_id} недоступен для отправки предложения о созвоне: {e}")
            else:
                logger.error(f"Telegram API ошибка при отправке предложения о созвоне пользователю {user_id}: {e}")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка отправки предложения о созвоне пользователю {user_id}: {e}", exc_info=True)

