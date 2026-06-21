import logging
import traceback
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import ErrorLog
from typing import Optional

logger = logging.getLogger(__name__)

class ErrorLoggingService:
    """Сервис для логирования ошибок в базу данных"""
    
    @staticmethod
    def log_error(
        error_type: str,
        error_message: str,
        error_traceback: Optional[str] = None,
        function_name: Optional[str] = None,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        severity: str = 'error'
    ):
        """Логирует ошибку в базу данных"""
        db = SessionLocal()
        try:
            error_log = ErrorLog(
                error_type=error_type,
                error_message=error_message[:1000],  # Ограничиваем длину сообщения
                error_traceback=error_traceback[:5000] if error_traceback else None,  # Ограничиваем трейсбек
                function_name=function_name,
                user_id=user_id,
                chat_id=chat_id,
                severity=severity,
                created_at=datetime.utcnow()
            )
            db.add(error_log)
            db.commit()
            logger.debug(f"Ошибка залогирована в БД: {error_type} в {function_name}")
        except Exception as e:
            logger.error(f"Ошибка при логировании ошибки в БД: {e}", exc_info=True)
            db.rollback()
        finally:
            db.close()
    
    @staticmethod
    def get_recent_errors(limit: int = 50, severity: Optional[str] = None, hours: Optional[int] = None):
        """Получает последние ошибки из БД"""
        db = SessionLocal()
        try:
            query = db.query(ErrorLog)
            
            if severity:
                query = query.filter(ErrorLog.severity == severity)
            
            if hours:
                since = datetime.utcnow() - timedelta(hours=hours)
                query = query.filter(ErrorLog.created_at >= since)
            
            query = query.order_by(ErrorLog.created_at.desc())
            errors = query.limit(limit).all()
            return errors
        except Exception as e:
            logger.error(f"Ошибка при получении ошибок из БД: {e}", exc_info=True)
            return []
        finally:
            db.close()
    
    @staticmethod
    def mark_error_resolved(error_id: int):
        """Отмечает ошибку как решенную"""
        db = SessionLocal()
        try:
            error = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()
            if error:
                error.is_resolved = True
                db.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при отметке ошибки как решенной: {e}", exc_info=True)
            db.rollback()
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_error_statistics():
        """Получает статистику по ошибкам"""
        db = SessionLocal()
        try:
            total = db.query(ErrorLog).count()
            unresolved = db.query(ErrorLog).filter(ErrorLog.is_resolved == False).count()
            critical = db.query(ErrorLog).filter(ErrorLog.severity == 'critical').count()
            last_24h = db.query(ErrorLog).filter(
                ErrorLog.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).count()
            
            return {
                'total': total,
                'unresolved': unresolved,
                'critical': critical,
                'last_24h': last_24h
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики ошибок: {e}", exc_info=True)
            return {'total': 0, 'unresolved': 0, 'critical': 0, 'last_24h': 0}
        finally:
            db.close()

