import logging
from datetime import datetime
from database.connection import SessionLocal
from database.models import PaymentLinkUsage, User, Payment

logger = logging.getLogger(__name__)

class LinkProtectionService:
    """Сервис для защиты от повторного использования ссылок на оплату"""
    
    @staticmethod
    def can_use_payment_link(user_id: int, payment_id: str) -> bool:
        """
        Проверяет, может ли пользователь использовать ссылку на оплату.
        Логика: если количество покупок > количества использований ссылок, то можно.
        """
        db = SessionLocal()
        try:
            # Получаем количество успешных покупок пользователя
            successful_purchases = db.query(Payment).filter(
                Payment.user_id == user_id,
                Payment.status == 'succeeded'
            ).count()
            
            # Получаем количество использований ссылок
            link_usages = db.query(PaymentLinkUsage).filter(
                PaymentLinkUsage.user_id == user_id,
                PaymentLinkUsage.link_used == True
            ).count()
            
            # Если покупок больше чем использований ссылок - можно использовать
            can_use = successful_purchases > link_usages
            
            logger.info(f"[LinkProtection] Пользователь {user_id}: покупок={successful_purchases}, использований={link_usages}, может_использовать={can_use}")
            return can_use
            
        except Exception as e:
            logger.error(f"[LinkProtection] Ошибка проверки ссылки для пользователя {user_id}: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def mark_link_as_used(user_id: int, payment_id: str) -> bool:
        """Отмечает ссылку как использованную"""
        db = SessionLocal()
        try:
            # Создаем или обновляем запись об использовании ссылки
            link_usage = db.query(PaymentLinkUsage).filter(
                PaymentLinkUsage.user_id == user_id,
                PaymentLinkUsage.payment_id == payment_id
            ).first()
            
            if not link_usage:
                link_usage = PaymentLinkUsage(
                    user_id=user_id,
                    payment_id=payment_id,
                    link_used=True,
                    used_at=datetime.utcnow()
                )
                db.add(link_usage)
            else:
                link_usage.link_used = True
                link_usage.used_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"[LinkProtection] Ссылка {payment_id} отмечена как использованная для пользователя {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[LinkProtection] Ошибка отметки ссылки как использованной: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def create_payment_link_record(user_id: int, payment_id: str) -> bool:
        """Создает запись о новой ссылке на оплату"""
        db = SessionLocal()
        try:
            # Проверяем, есть ли уже запись для этого платежа
            existing = db.query(PaymentLinkUsage).filter(
                PaymentLinkUsage.user_id == user_id,
                PaymentLinkUsage.payment_id == payment_id
            ).first()
            
            if not existing:
                link_usage = PaymentLinkUsage(
                    user_id=user_id,
                    payment_id=payment_id,
                    link_used=False
                )
                db.add(link_usage)
                db.commit()
                logger.info(f"[LinkProtection] Создана запись о ссылке {payment_id} для пользователя {user_id}")
                return True
            else:
                logger.info(f"[LinkProtection] Запись о ссылке {payment_id} уже существует для пользователя {user_id}")
                return True
                
        except Exception as e:
            logger.error(f"[LinkProtection] Ошибка создания записи о ссылке: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def reset_user_link_usage(user_id: int) -> bool:
        """Сбрасывает использование ссылок для пользователя (при новой покупке)"""
        db = SessionLocal()
        try:
            # Удаляем все записи об использовании ссылок для пользователя
            db.query(PaymentLinkUsage).filter(
                PaymentLinkUsage.user_id == user_id
            ).delete()
            
            db.commit()
            logger.info(f"[LinkProtection] Сброшено использование ссылок для пользователя {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[LinkProtection] Ошибка сброса использования ссылок: {e}")
            db.rollback()
            return False
        finally:
            db.close()
