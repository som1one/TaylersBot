import logging
import functools
import telebot
import traceback

logger = logging.getLogger(__name__)

# Импортируем сервис логирования ошибок
try:
    from services.error_logging_service import ErrorLoggingService
    ERROR_LOGGING_ENABLED = True
except ImportError:
    ERROR_LOGGING_ENABLED = False

def safe_handler(func):
    """Декоратор для безопасной обработки ошибок в обработчиках бота"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except telebot.apihelper.ApiTelegramException as e:
            # Ошибки API Telegram - логируем, но не падаем
            logger.error(f"Telegram API ошибка в {func.__name__}: {e}", exc_info=True)
            try:
                # Пытаемся отправить сообщение об ошибке пользователю, если это возможно
                if args and hasattr(args[0], 'chat') and hasattr(args[0].chat, 'id'):
                    message = args[0]
                    bot = kwargs.get('bot') or (message.bot if hasattr(message, 'bot') else None)
                    if bot:
                        bot.send_message(message.chat.id, "⚠️ Произошла ошибка при обработке запроса. Попробуйте позже.")
                elif args and hasattr(args[0], 'message') and hasattr(args[0].message, 'chat'):
                    call = args[0]
                    bot = kwargs.get('bot') or (call.bot if hasattr(call, 'bot') else None)
                    if bot:
                        bot.answer_callback_query(call.id, "❌ Ошибка обработки запроса")
                        try:
                            bot.send_message(call.message.chat.id, "⚠️ Произошла ошибка. Попробуйте позже.")
                        except:
                            pass
            except Exception:
                pass
            return None
        except Exception as e:
            # Все остальные ошибки - логируем с полным трейсом
            logger.error(f"Непредвиденная ошибка в {func.__name__}: {e}", exc_info=True)
            try:
                # Пытаемся отправить сообщение об ошибке пользователю
                if args and hasattr(args[0], 'chat') and hasattr(args[0].chat, 'id'):
                    message = args[0]
                    bot = kwargs.get('bot') or (message.bot if hasattr(message, 'bot') else None)
                    if bot:
                        bot.send_message(message.chat.id, "⚠️ Произошла внутренняя ошибка. Попробуйте позже или обратитесь в поддержку.")
                elif args and hasattr(args[0], 'message') and hasattr(args[0].message, 'chat'):
                    call = args[0]
                    bot = kwargs.get('bot') or (call.bot if hasattr(call, 'bot') else None)
                    if bot:
                        bot.answer_callback_query(call.id, "❌ Ошибка")
                        try:
                            bot.send_message(call.message.chat.id, "⚠️ Произошла внутренняя ошибка. Попробуйте позже.")
                        except:
                            pass
            except Exception:
                pass
            return None
    return wrapper

def safe_send_message(bot, chat_id, text, **kwargs):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        logger.warning(f"Ошибка отправки сообщения в {chat_id}: {e}")
        if ERROR_LOGGING_ENABLED:
            ErrorLoggingService.log_error(
                error_type='ApiTelegramException',
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                function_name='safe_send_message',
                chat_id=chat_id,
                severity='warning'
            )
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при отправке сообщения в {chat_id}: {e}", exc_info=True)
        if ERROR_LOGGING_ENABLED:
            ErrorLoggingService.log_error(
                error_type=type(e).__name__,
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                function_name='safe_send_message',
                chat_id=chat_id,
                severity='error'
            )
        return None

def safe_edit_message_text(bot, chat_id, message_id, text, **kwargs):
    """Безопасное редактирование сообщения с обработкой ошибок"""
    try:
        return bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        error_msg = str(e).lower()
        # Если сообщение не изменилось - это нормально, просто логируем
        if "message is not modified" in error_msg:
            logger.debug(f"Сообщение {message_id} в {chat_id} не изменилось")
            return None
        # Если не удалось отредактировать, отправляем новое сообщение
        logger.warning(f"Не удалось отредактировать сообщение {message_id} в {chat_id}: {e}")
        try:
            # Убираем reply_markup из kwargs для fallback, так как он может вызвать ошибку
            fallback_kwargs = {k: v for k, v in kwargs.items() if k not in ['parse_mode', 'reply_markup']}
            return bot.send_message(chat_id, text, **fallback_kwargs)
        except Exception as send_e:
            logger.warning(f"Не удалось отправить fallback сообщение в {chat_id}: {send_e}")
            return None
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения {message_id} в {chat_id}: {e}", exc_info=True)
        return None

def safe_answer_callback(bot, callback_query_id, text=None, show_alert=False):
    """Безопасный ответ на callback query"""
    try:
        return bot.answer_callback_query(callback_query_id, text=text, show_alert=show_alert)
    except Exception as e:
        logger.warning(f"Ошибка ответа на callback query {callback_query_id}: {e}")
        if ERROR_LOGGING_ENABLED:
            ErrorLoggingService.log_error(
                error_type=type(e).__name__,
                error_message=str(e),
                error_traceback=traceback.format_exc(),
                function_name='safe_answer_callback',
                severity='warning'
            )
        return None

