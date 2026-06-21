import logging
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from database.connection import SessionLocal
from database.models import User, Subscription, Payment, AmbassadorStats, Ambassador
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class StatisticsService:
    def __init__(self):
        pass
    
    def get_bot_statistics(self):
        """Получает общую статистику бота"""
        db = SessionLocal()
        try:
            total_users = db.query(func.count(User.id)).scalar()

            # Количество амбассадоров с ожидающей выплатой, если таблица Ambassador используется
            try:
                ambassadors_awaiting_payment = db.query(func.count(Ambassador.id)).filter(
                    Ambassador.pending_payout > 0
                ).scalar()
            except Exception:
                ambassadors_awaiting_payment = 0

            total_active_subscriptions = db.query(func.count(Subscription.id)).filter(
                Subscription.is_active == True
            ).scalar()

            purchased_subscriptions = db.query(func.count(func.distinct(Subscription.id))).join(
                Payment, Subscription.id == Payment.subscription_id
            ).filter(
                Payment.status == "succeeded"
            ).scalar()

            admin_issued_subscriptions = db.query(func.count(Subscription.id)).outerjoin(
                Payment, Subscription.id == Payment.subscription_id
            ).filter(
                Subscription.is_active == True,
                Payment.id.is_(None)
            ).scalar()

            other_subscriptions = total_active_subscriptions - purchased_subscriptions - admin_issued_subscriptions

            now = datetime.utcnow()
            last_24h = now - timedelta(hours=24)
            last_48h = now - timedelta(hours=48)
            last_7d = now - timedelta(days=7)
            
            new_24h = db.query(func.count(Subscription.id)).filter(
                and_(
                    Subscription.created_at >= last_24h,
                    Subscription.is_active == True
                )
            ).scalar()
            
            new_48h = db.query(func.count(Subscription.id)).filter(
                and_(
                    Subscription.created_at >= last_48h,
                    Subscription.is_active == True
                )
            ).scalar()
            
            new_7d = db.query(func.count(Subscription.id)).filter(
                and_(
                    Subscription.created_at >= last_7d,
                    Subscription.is_active == True
                )
            ).scalar()
            
            return {
                "total_users": total_users,
                "ambassadors_awaiting_payment": ambassadors_awaiting_payment,
                "total_active_subscriptions": total_active_subscriptions,
                "purchased_subscriptions": purchased_subscriptions,
                "admin_issued_subscriptions": admin_issued_subscriptions,
                "other_subscriptions": other_subscriptions,
                "dynamics": {
                    "last_24h": new_24h,
                    "last_48h": new_48h,
                    "last_7d": new_7d
                }
            }
        finally:
            db.close()
    
    def get_ambassadors_list(self):
        """Получает список амбассадоров с их статистикой"""
        db = SessionLocal()
        try:
            ambassadors = db.query(User).filter(User.is_ambassador == True).all()
            result = []

            for ambassador in ambassadors:
                transitions = 0
                paid_users = 0
                awaiting_payment = 0
                try:
                    transitions = db.query(func.count(AmbassadorStats.id)).filter(
                        and_(
                            AmbassadorStats.user_id == ambassador.telegram_id,
                            AmbassadorStats.action_type == "click"
                        )
                    ).scalar()
                except Exception:
                    transitions = 0
                try:
                    paid_users = db.query(func.count(func.distinct(AmbassadorStats.referral_id))).filter(
                        and_(
                            AmbassadorStats.user_id == ambassador.telegram_id,
                            AmbassadorStats.action_type == "payment"
                        )
                    ).scalar()
                except Exception:
                    paid_users = 0
                try:
                    awaiting_payment = db.query(func.count(func.distinct(AmbassadorStats.referral_id))).join(
                        Subscription, AmbassadorStats.referral_id == Subscription.user_id
                    ).filter(
                        and_(
                            AmbassadorStats.user_id == ambassador.telegram_id,
                            AmbassadorStats.action_type == "subscription",
                            Subscription.is_active == True
                        )
                    ).scalar()
                except Exception:
                    awaiting_payment = 0

                result.append({
                    "username": ambassador.username or f"user_{ambassador.telegram_id}",
                    "telegram_id": ambassador.telegram_id,
                    "transitions": transitions,
                    "paid_users": paid_users,
                    "awaiting_payment": awaiting_payment
                })

            return result
        except Exception as e:
            logger.error(f"[get_ambassadors_list] Ошибка: {e}")
            return []
        finally:
            db.close()
    
    def track_ambassador_action(self, ambassador_id: int, referral_id: int, action_type: str):
        """Отслеживает действие амбассадора"""
        db = SessionLocal()
        try:
            ambassador = db.query(User).filter(
                and_(
                    User.telegram_id == ambassador_id,
                    User.is_ambassador == True
                )
            ).first()
            
            if not ambassador:
                logger.warning(f"Пользователь {ambassador_id} не является амбассадором")
                return False

            stats = AmbassadorStats(
                user_id=ambassador_id,
                referral_id=referral_id,
                action_type=action_type
            )
            db.add(stats)
            db.commit()
            
            logger.info(f"Отслежено действие амбассадора {ambassador_id}: {action_type} для {referral_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отслеживания действия амбассадора: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def make_user_ambassador(self, telegram_id: int, ambassador_code: str = None):
        """Делает пользователя амбассадором"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                logger.warning(f"Пользователь с telegram_id {telegram_id} не найден.")
                return False
            
            if not ambassador_code:
                ambassador_code = str(telegram_id)
            
            user.is_ambassador = True
            user.ambassador_code = ambassador_code
            db.commit()
            
            logger.info(f"Пользователь {telegram_id} стал амбассадором с кодом {ambassador_code}")
            return True
        except Exception as e:
            logger.error(f"Ошибка назначения амбассадора: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def remove_user_ambassador(self, telegram_id: int):
        """Делает пользователя обычным пользователем (удаляет статус амбассадора)"""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                logger.warning(f"Пользователь с telegram_id {telegram_id} не найден.")
                return False
            
            if not user.is_ambassador:
                logger.warning(f"Пользователь {telegram_id} не является амбассадором, удаление невозможно.")
                return False
            
            user.is_ambassador = False
            user.ambassador_code = None
            db.commit()
            
            logger.info(f"Пользователь {telegram_id} успешно удален из амбассадоров.")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления амбассадора: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def get_user_referral_stats(self, user_id: int):
        """Получает статистику рефералов пользователя"""
        db = SessionLocal()
        try:
            # user_id интерпретируем как telegram_id, т.к. User.referred_by хранит telegram_id
            total_referrals = db.query(func.count(User.id)).filter(
                User.referred_by == user_id
            ).scalar()

            active_referrals = db.query(func.count(func.distinct(User.telegram_id))).join(
                Subscription, User.telegram_id == Subscription.user_id
            ).filter(
                and_(
                    User.referred_by == user_id,
                    Subscription.is_active == True
                )
            ).scalar()

            paid_referrals = db.query(func.count(func.distinct(User.telegram_id))).join(
                Payment, User.telegram_id == Payment.user_id
            ).filter(
                and_(
                    User.referred_by == user_id,
                    Payment.status == "succeeded"
                )
            ).scalar()
            
            return {
                "total_referrals": total_referrals,
                "active_referrals": active_referrals,
                "paid_referrals": paid_referrals
            }
        finally:
            db.close()

    def has_user_clicked_referral(self, ambassador_id: int, referral_id: int) -> bool:
        """Проверяет, засчитан ли уже клик по реферальной ссылке referral_id для данного амбассадора (ambassador_id)."""
        db = SessionLocal()
        try:
            exists_q = db.query(AmbassadorStats.id).filter(
                and_(
                    AmbassadorStats.user_id == ambassador_id,
                    AmbassadorStats.referral_id == referral_id,
                    AmbassadorStats.action_type == "click"
                )
            ).first()
            return exists_q is not None
        finally:
            db.close()

    @staticmethod
    def get_total_users():
        db = SessionLocal()
        try:
            return db.query(User).count()
        except Exception as e:
            logger.error(f"[get_total_users] Ошибка: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_ambassadors_pending_payout():
        db = SessionLocal()
        try:
            # Считаем только пользователей с is_ambassador == True и у которых есть pending_payout > 0
            return db.query(User).filter(User.is_ambassador == True, User.total_spent > 0).count()
        except Exception as e:
            logger.error(f"[get_ambassadors_pending_payout] Ошибка: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_total_active_subscriptions():
        db = SessionLocal()
        try:
            return db.query(Subscription).filter(
                Subscription.is_active == True,
                Subscription.end_date > datetime.utcnow()
            ).count()
        except Exception as e:
            logger.error(f"[get_total_active_subscriptions] Ошибка: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_purchased_subscriptions_count():
        db = SessionLocal()
        try:
            return db.query(Subscription).join(Payment).filter(
                Subscription.is_active == True,
                Subscription.end_date > datetime.utcnow(),
                Payment.status == 'succeeded'
            ).count()
        except Exception as e:
            logger.error(f"[get_purchased_subscriptions_count] Ошибка: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_admin_issued_subscriptions_count():
        db = SessionLocal()
        try:
            return db.query(Subscription).outerjoin(
                Payment, Subscription.id == Payment.subscription_id
            ).filter(
                Subscription.is_active == True,
                Subscription.end_date > datetime.utcnow(),
                Payment.id.is_(None)
            ).count()
        except Exception as e:
            logger.error(f"[get_admin_issued_subscriptions_count] Ошибка: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_other_subscriptions_count():
        return 0

    @staticmethod
    def get_new_active_subscriptions_dynamic(hours: int):
        db = SessionLocal()
        try:
            time_threshold = datetime.utcnow() - timedelta(hours=hours)
            return db.query(Subscription).filter(
                Subscription.is_active == True,
                Subscription.start_date >= time_threshold
            ).count()
        except Exception as e:
            logger.error(f"[get_new_active_subscriptions_dynamic] Ошибка: {e}")
            return 0
        finally:
            db.close()
