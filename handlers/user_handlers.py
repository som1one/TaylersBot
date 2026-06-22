import telebot
from telebot import types
from services.user_service import UserService
from services.payment_service_alt import PaymentService
from services.telegram_channel_service import TelegramChannelService
from services.link_protection_service import LinkProtectionService
from services.marathon_service import MarathonService
from database.models import Tariff, PromoCode, Subscription, User
from database.connection import SessionLocal
from config import Config
from datetime import datetime, timedelta
import logging
from handlers.error_handler import safe_send_message, safe_edit_message_text, safe_answer_callback, strip_premium_emoji

logger = logging.getLogger(__name__)

def register_user_handlers(bot, payment_service=None, telegram_channel_service=None):
    if telegram_channel_service is None:
        telegram_channel_service = TelegramChannelService(bot)
    if payment_service is None:
        payment_service = PaymentService(telegram_channel_service=telegram_channel_service)
    
    user_tariff_purchase = {}
    message_cache = {}  # Кэш для предотвращения дублирования сообщений
    
    def update_user_activity(user_telegram_id):
        """Обновляет активность пользователя"""
        try:
            from services.user_activity_service import UserActivityService
            temp_activity_service = UserActivityService(bot)
            temp_activity_service.update_user_activity(user_telegram_id)
        except Exception as e:
            logger.error(f"Ошибка обновления активности пользователя {user_telegram_id}: {e}")

    # ==============================
    # Вспомогательная функция
    # ==============================
    def format_duration(days: int | None) -> str:
        """Форматирует количество дней подписки."""
        if not days or days >= 36500:
            return "Навсегда"
        d = int(days)
        if d % 10 == 1 and d % 100 != 11:
            suffix = "день"
        elif d % 10 in (2, 3, 4) and (d % 100 not in (12, 13, 14)):
            suffix = "дня"
        else:
            suffix = "дней"
        return f"{d} {suffix}"

    def main_menu_markup():
        """Возвращает стандартную клавиатуру главного меню для всех пользователей."""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('💰 Тарифы', '📱 Моя подписка', 'ℹ️ Помощь')
        return markup

    # ==============================
    # /start
    # ==============================
    @bot.message_handler(commands=['start'])
    def start_handler(message):
        logger.info(f"[start_handler] Получена команда /start от пользователя {message.from_user.id}")
        user_telegram_id = message.from_user.id
        chat_id = message.chat.id
        
        # Обновляем активность пользователя
        update_user_activity(user_telegram_id)
        
        referred_by_ambassador_id = None
        if message.text and len(message.text.split()) > 1:
            try:
                referral_param = message.text.split()[1]
                referred_by_ambassador_id = int(referral_param)
                logger.info(f"[start_handler] Обнаружен referral_param: {referral_param}, converted to ID: {referred_by_ambassador_id}")
            except ValueError as e:
                logger.error(f"[start_handler] Ошибка при парсинге referral_param '{referral_param}': {e}")
                referred_by_ambassador_id = None

        logger.info(f"[start_handler] referred_by_ambassador_id после обработки: {referred_by_ambassador_id}")

        # Создание или получение пользователя
        try:
            user = UserService.get_or_create_user(
                telegram_id=user_telegram_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referred_by=referred_by_ambassador_id
            )
            logger.info(f"[start_handler] Пользователь {user_telegram_id} получен/создан. ID: {user.id}, Username: {user.username}")
        except Exception as e:
            logger.error(f"[start_handler] Ошибка при получении/создании пользователя {user_telegram_id}: {e}", exc_info=True)
            safe_send_message(bot, chat_id, "Произошла внутренняя ошибка при инициализации. Пожалуйста, попробуйте еще раз позже.")
            return

        # Проверяем, чтобы пользователь не мог повторно активировать ссылку
        if referred_by_ambassador_id and user.referred_by == referred_by_ambassador_id:
            try:
                from services.statistics_service import StatisticsService
                statistics_service = StatisticsService()

                # Проверяем, не кликал ли уже этот юзер по ссылке этого амбассадора
                if not statistics_service.has_user_clicked_referral(referred_by_ambassador_id, user.telegram_id):
                    statistics_service.track_ambassador_action(referred_by_ambassador_id, user.telegram_id, "click")
                    safe_send_message(bot, chat_id, "Спасибо, что пришли по реферальной ссылке!")
                    logger.info(f"[start_handler] Засчитан клик по реферальной ссылке для {user_telegram_id}")
                else:
                    logger.info(f"[start_handler] Пользователь {user_telegram_id} уже кликал по ссылке {referred_by_ambassador_id}, повтор не засчитывается.")
            except Exception as e:
                logger.error(f"[start_handler] Ошибка при отслеживании амбассадора для {user_telegram_id}: {e}", exc_info=True)

        # Инициализируем статус пользователя в марафоне (только если его еще нет)
        try:
            db = SessionLocal()
            try:
                from database.models import UserMarathonStatus
                existing_status = db.query(UserMarathonStatus).filter_by(user_id=user_telegram_id).first()
                if not existing_status:
                    MarathonService.get_or_create_user_status(user_telegram_id)
                    logger.info(f"[start_handler] Создан статус марафона для нового пользователя {user_telegram_id}")
                else:
                    logger.debug(f"[start_handler] Статус марафона уже существует для пользователя {user_telegram_id}")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[start_handler] Ошибка создания статуса пользователя {user_telegram_id}: {e}", exc_info=True)

        # Отправляем приветствие и обучалку
        try:
            # Проверяем категорию пользователя (можно расширить логику)
            category_message = MarathonService.get_category_message()
            if category_message and category_message.text_content:
                safe_send_message(bot, chat_id, category_message.text_content)
            # Пропускаем, если сообщения категории нет - это нормально
            
            # Отправляем обучающее видео (пропускаем, если нет в БД)
            try:
                training_video = MarathonService.get_training_video()
                if training_video:
                    try:
                        if training_video.file_id and training_video.file_type == 'video':
                            bot.send_video(chat_id, training_video.file_id, caption=training_video.title or training_video.description)
                        elif training_video.file_id and training_video.file_type == 'photo':
                            bot.send_photo(chat_id, training_video.file_id, caption=training_video.title or training_video.description)
                        else:
                            # Если только текст
                            text = training_video.title or ""
                            if training_video.description:
                                text += f"\n\n{training_video.description}"
                            if text:
                                safe_send_message(bot, chat_id, text)
                        logger.info(f"[start_handler] Обучалка отправлена пользователю {user_telegram_id}")
                    except Exception as e:
                        logger.warning(f"[start_handler] Ошибка отправки обучалки пользователю {user_telegram_id}: {e}")
            except Exception as e:
                logger.warning(f"[start_handler] Ошибка получения обучалки для пользователя {user_telegram_id}: {e}")
            # Пропускаем, если обучалки нет в БД - это нормально, не логируем как ошибку
            
            # Создаем клавиатуру с кнопками
            try:
                safe_send_message(
                    bot,
                    chat_id,
                    "Выберите действие:",
                    reply_markup=main_menu_markup()
                )

                logger.info(f"[start_handler] Отправлено приветственное сообщение и клавиатура для {user_telegram_id}")
            except Exception as e:
                logger.error(f"[start_handler] Ошибка создания клавиатуры для {user_telegram_id}: {e}", exc_info=True)
                # Пытаемся отправить без клавиатуры
                safe_send_message(bot, chat_id, "Выберите действие из меню бота.")
                
        except Exception as e:
            logger.error(f"[start_handler] Ошибка при отправке приветственного сообщения и клавиатуры для {user_telegram_id}: {e}", exc_info=True)

    @bot.message_handler(func=lambda m: m.text == '💰 Тарифы')
    def show_tariffs(message):
        logger.info(f"[show_tariffs] Получено нажатие кнопки 'Тарифы' от пользователя {message.from_user.id}")
        
        # Обновляем активность пользователя
        update_user_activity(message.from_user.id)
        db = SessionLocal()
        try:
            tariffs = db.query(Tariff).filter(Tariff.is_active == True).all()
            if not tariffs:
                safe_send_message(bot, message.chat.id, "😔 К сожалению, сейчас нет доступных тарифов.")
                logger.warning(f"[show_tariffs] Нет активных тарифов для пользователя {message.from_user.id}")
                return
            text = "💰 Доступные тарифы:\n\nВыберите тариф, чтобы узнать подробности:"
            markup = types.InlineKeyboardMarkup()
            for tariff in tariffs:
                markup.add(types.InlineKeyboardButton(f"{tariff.name} — {tariff.price}₽", callback_data=f"view_tariff_{tariff.id}"))
            safe_send_message(bot, message.chat.id, text, reply_markup=markup)
            logger.info(f"[show_tariffs] Отправлены доступные тарифы для пользователя {message.from_user.id}")
        finally:
            db.close()

    @bot.message_handler(func=lambda m: m.text == '📱 Моя подписка')
    def show_subscription(message):
        logger.info(f"[show_subscription] Получено нажатие кнопки 'Моя подписка' от пользователя {message.from_user.id}")
        user = UserService.get_user_by_telegram_id(message.from_user.id)
        if not user:
            safe_send_message(bot, message.chat.id, "❌ Пользователь не найден.")
            logger.warning(f"[show_subscription] Пользователь {message.from_user.id} не найден.")
            return
        db = SessionLocal()
        try:
            subscription = UserService.get_active_subscription(user.telegram_id)
            if not subscription:
                text = "📱 У вас нет активной подписки.\n\n💡 Оформите подписку, чтобы получить доступ к премиум функциям!"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💰 Посмотреть тарифы", callback_data="show_tariffs"))
                safe_send_message(bot, message.chat.id, text, reply_markup=markup)
                logger.info(f"[show_subscription] У пользователя {user.telegram_id} нет активной подписки. Отправлено сообщение без подписки.")
            else:
                tariff = db.query(Tariff).filter(Tariff.id == subscription.tariff_id).first()
                text = f"📱 Ваша подписка:\n\n"
                text += f"📦 Тариф: {tariff.name if tariff else 'Неизвестный тариф'}\n"
                text += f"📅 Дата начала: {subscription.start_date.strftime('%d.%m.%Y')}\n"
                text += f"📅 Дата окончания: {subscription.end_date.strftime('%d.%m.%Y') if subscription.end_date.year < 2100 else 'Навсегда'}\n"
                text += f"⏱️ Длительность тарифа: {format_duration(tariff.duration_days if tariff else None)}\n"
                text += f"✅ Статус: Активна"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("💰 Посмотреть тарифы", callback_data="show_tariffs"))
                safe_send_message(bot, message.chat.id, text, reply_markup=markup)
                logger.info(f"[show_subscription] Отправлена информация об активной подписке для пользователя {user.telegram_id}.")
        except Exception as e:
            logger.error(f"[show_subscription] Ошибка при отображении подписки для пользователя {message.from_user.id}: {e}", exc_info=True)
            safe_send_message(bot, message.chat.id, "Произошла ошибка при получении информации о подписке.")
        finally:
            db.close()

    @bot.message_handler(func=lambda m: m.text == 'ℹ️ Помощь' or (m.text and m.text.lower() == '/help'))
    def help_command(message):
        logger.info(f"[help_command] Получено нажатие кнопки 'Помощь' или команда /help от пользователя {message.from_user.id}")
        try:
            text = (
                "ℹ️ Помощь\n\n"
                "Если у вас возникли вопросы, обратитесь к @deltasmaxxx.\n"
            )
            safe_send_message(bot, message.chat.id, text)
            logger.info(f"[help_command] Отправлено сообщение помощи для пользователя {message.from_user.id}")
        except Exception as e:
            logger.error(f"[help_command] Ошибка при отправке сообщения помощи для пользователя {message.from_user.id}: {e}", exc_info=True)
            safe_send_message(bot, message.chat.id, "Произошла ошибка при получении информации о помощи.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_tariff_') or call.data.startswith('view_tariff_') or call.data == 'show_tariffs')
    def handle_tariff_callback(call):
        logger.info(f"[handle_tariff_callback] Получен callback_query: {call.data} от пользователя {call.from_user.id}")
        if call.data.startswith('view_tariff_'):
            tariff_id = int(call.data.split('_')[2])
            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if not tariff:
                    safe_answer_callback(bot, call.id, "❌ Тариф не найден.")
                    return
                description_clean = strip_premium_emoji(tariff.description or '')
                text = (
                    f"📦 {tariff.name}\n"
                    f"💰 Цена: {tariff.price}₽\n"
                    f"⏱️ Длительность: {format_duration(tariff.duration_days)}\n"
                )
                if description_clean:
                    text += f"\n{description_clean}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(f"Купить {tariff.name} - {tariff.price}₽", callback_data=f"buy_tariff_{tariff.id}"))
                markup.add(types.InlineKeyboardButton("← Назад к тарифам", callback_data="show_tariffs"))
                safe_send_message(bot, call.message.chat.id, text, reply_markup=markup)
                logger.info(f"[handle_tariff_callback] Показан тариф {tariff_id} для пользователя {call.from_user.id}")
            except Exception as e:
                logger.error(f"[handle_tariff_callback] Ошибка при показе тарифа {tariff_id} для {call.from_user.id}: {e}", exc_info=True)
                safe_answer_callback(bot, call.id, "❌ Произошла ошибка.")
            finally:
                db.close()
        elif call.data.startswith('buy_tariff_'):
            tariff_id = int(call.data.split('_')[2])
            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if not tariff:
                    safe_answer_callback(bot, call.id, "❌ Тариф не найден.")
                    logger.warning(f"[handle_tariff_callback] Тариф с ID {tariff_id} не найден.")
                    return
                user = UserService.get_user_by_telegram_id(call.from_user.id)
                if not user:
                    safe_answer_callback(bot, call.id, "❌ Пользователь не найден.")
                    logger.warning(f"[handle_tariff_callback] Пользователь {call.from_user.id} не найден.")
                    return
                user_tariff_purchase[call.from_user.id] = {'tariff_id': tariff_id}
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.add('Пропустить')
                safe_send_message(bot, call.message.chat.id, "Если у вас есть промокод, введите его сейчас или нажмите 'Пропустить':", reply_markup=markup)
                try:
                    bot.register_next_step_handler(call.message, handle_promocode_step, tariff)
                except Exception as e:
                    logger.error(f"[handle_tariff_callback] Ошибка регистрации next_step_handler: {e}", exc_info=True)
                logger.info(f"[handle_tariff_callback] Запрос промокода для пользователя {call.from_user.id} для тарифа {tariff_id}")
            except Exception as e:
                logger.error(f"[handle_tariff_callback] Ошибка при обработке покупки тарифа для {call.from_user.id}: {e}", exc_info=True)
                safe_answer_callback(bot, call.id, "❌ Произошла ошибка при обработке запроса.")
            finally:
                db.close()
        elif call.data == 'show_tariffs':
            logger.info(f"[handle_tariff_callback] Вызов show_tariffs из callback для пользователя {call.from_user.id}")
            show_tariffs(call.message)

    def handle_promocode_step(message, tariff):
        logger.info(f"[handle_promocode_step] Получен промокод/пропуск от пользователя {message.from_user.id}. Текст: {message.text}")
        db = SessionLocal()
        try:
            promo = None
            discount = 0
            free_days = None
            code = message.text.strip().upper()
            if code != 'ПРОПУСТИТЬ':
                promo = db.query(PromoCode).filter(PromoCode.code == code, PromoCode.is_active == True).first()
                if not promo:
                    safe_send_message(bot, message.chat.id, "❌ Промокод не найден или неактивен. Попробуйте снова или нажмите 'Пропустить':")
                    try:
                        bot.register_next_step_handler(message, handle_promocode_step, tariff)
                    except Exception as e:
                        logger.error(f"[handle_promocode_step] Ошибка регистрации next_step_handler: {e}", exc_info=True)
                    logger.warning(f"[handle_promocode_step] Промокод '{code}' не найден или неактивен для пользователя {message.from_user.id}")
                    return
                if promo.expires_at and promo.expires_at < datetime.utcnow():
                    promo.is_active = False
                    db.commit()
                    safe_send_message(bot, message.chat.id, "❌ Срок действия промокода истёк. Промокод деактивирован. Попробуйте другой или нажмите 'Пропустить':")
                    try:
                        bot.register_next_step_handler(message, handle_promocode_step, tariff)
                    except Exception as e:
                        logger.error(f"[handle_promocode_step] Ошибка регистрации next_step_handler: {e}", exc_info=True)
                    logger.warning(f"[handle_promocode_step] Промокод '{code}' истёк и деактивирован для пользователя {message.from_user.id}")
                    return
                if promo.usage_limit and promo.usage_count >= promo.usage_limit:
                    promo.is_active = False
                    db.commit()
                    safe_send_message(bot, message.chat.id, "❌ Промокод уже использован максимальное число раз. Промокод деактивирован. Попробуйте другой или нажмите 'Пропустить':")
                    try:
                        bot.register_next_step_handler(message, handle_promocode_step, tariff)
                    except Exception as e:
                        logger.error(f"[handle_promocode_step] Ошибка регистрации next_step_handler: {e}", exc_info=True)
                    logger.warning(f"[handle_promocode_step] Промокод '{code}' достиг лимита использования и деактивирован для пользователя {message.from_user.id}")
                    return
                if promo.is_free:
                    free_days = promo.duration_days or 30
                    logger.info(f"[handle_promocode_step] Применён бесплатный промокод '{code}' на {free_days} дней для {message.from_user.id}")
                elif promo.discount_percent:
                    discount = promo.discount_percent
                    logger.info(f"[handle_promocode_step] Применён промокод '{code}' со скидкой {discount}% для {message.from_user.id}")
            else:
                logger.info(f"[handle_promocode_step] Пользователь {message.from_user.id} пропустил ввод промокода.")
            
            final_price = tariff.price
            duration_days = tariff.duration_days
            if free_days:
                final_price = 0
                duration_days = free_days
            elif discount:
                final_price = round(tariff.price * (1 - discount / 100), 2)
            
            text = f"Тариф: {tariff.name}\n"
            if free_days:
                text += f"Промокод: Бесплатно на {free_days} дней!\n"
            elif discount:
                text += f"Промокод: Скидка {discount}%\n"
            text += f"К оплате: {final_price}₽\n"
            text += f"Длительность: {format_duration(duration_days)}"
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            code_for_callback = code if code != 'ПРОПУСТИТЬ' else ''
            markup.add(types.InlineKeyboardButton(
                "💳 Оплатить картой",
                callback_data=f"pay_tariff_{tariff.id}_{final_price}_{duration_days or 0}_{code_for_callback}"
            ))
            # Кнопка криптовалюты только если бесплатной активации нет и кошелёк настроен
            if final_price > 0 and Config.CRYPTO_WALLET_ADDRESS:
                markup.add(types.InlineKeyboardButton(
                    "🪙 Оплатить криптой",
                    callback_data=f"pay_crypto_{tariff.id}_{final_price}_{duration_days or 0}_{code_for_callback}"
                ))
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment"))
            
            markup_menu = main_menu_markup()
            
            safe_send_message(bot, message.chat.id, text, reply_markup=markup, reply_to_message_id=message.message_id)
            logger.info(f"[handle_promocode_step] Отправлено сообщение с подтверждением оплаты для пользователя {message.from_user.id}")
        except Exception as e:
            logger.error(f"[handle_promocode_step] Ошибка при обработке промокода/оплаты для пользователя {message.from_user.id}: {e}", exc_info=True)
            safe_send_message(bot, message.chat.id, "Произошла ошибка при применении промокода или расчете оплаты.")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pay_tariff_'))
    def handle_pay_tariff(call):
        logger.info(f"[handle_pay_tariff] Получен callback_query: {call.data} от пользователя {call.from_user.id}")
        parts = call.data.split('_')
        tariff_id = int(parts[2])
        final_price = float(parts[3])
        duration_days = int(parts[4]) if parts[4] != '0' else None
        promocode = parts[5] if len(parts) > 5 and parts[5] else None
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            user = UserService.get_user_by_telegram_id(call.from_user.id)
            if not user or not tariff:
                safe_answer_callback(bot, call.id, "❌ Ошибка. Попробуйте снова.")
                logger.warning(f"[handle_pay_tariff] Пользователь {call.from_user.id} или тариф {tariff_id} не найден.")
                return
            
            if final_price == 0:
                now = datetime.utcnow()
                # Ищем существующую подписку для продления
                existing_sub = db.query(Subscription).filter_by(user_id=user.telegram_id).order_by(Subscription.created_at.desc()).first()
                
                if existing_sub:
                    # Продлеваем существующую подписку
                    if existing_sub.end_date and existing_sub.end_date > now:
                        # Подписка еще активна - продлеваем от даты окончания
                        existing_sub.end_date = existing_sub.end_date + timedelta(days=duration_days or 36500)
                    else:
                        # Подписка истекла - начинаем отсчет с текущего момента
                        existing_sub.end_date = now + timedelta(days=duration_days or 36500)
                        existing_sub.start_date = now
                    
                    existing_sub.is_active = True
                    existing_sub.reminder_sent = False
                    existing_sub.tariff_id = tariff.id  # Обновляем тариф
                    logger.info(f"[handle_pay_tariff] Подписка {existing_sub.id} продлена для пользователя {user.telegram_id}")
                else:
                    # Создаем новую подписку
                    end_date = now + timedelta(days=duration_days or 36500)
                    sub = Subscription(user_id=user.telegram_id, tariff_id=tariff.id, start_date=now, end_date=end_date, is_active=True)
                    db.add(sub)
                    logger.info(f"[handle_pay_tariff] Создана новая подписка для пользователя {user.telegram_id}")
                
                if promocode:
                    promo = db.query(PromoCode).filter(PromoCode.code == promocode).first()
                    if promo:
                        promo.usage_count = (promo.usage_count or 0) + 1
                
                db.commit()
                
                # Добавляем пользователя в канал, если еще не добавлен
                if telegram_channel_service:
                    try:
                        telegram_channel_service.add_user_to_channel(user.telegram_id)
                    except Exception as e:
                        logger.warning(f"[handle_pay_tariff] Не удалось добавить пользователя {user.telegram_id} в канал: {e}")
                
                safe_edit_message_text(bot, call.message.chat.id, call.message.message_id, "✅ Бесплатная подписка по промокоду активирована!")
                safe_send_message(bot, call.message.chat.id, "Выберите действие:", reply_markup=main_menu_markup())
                logger.info(f"[handle_pay_tariff] Бесплатная подписка активирована для {user.telegram_id} с промокодом {promocode}")
                return
            
            # Сохраняем промокод в метаданных платежа
            metadata = {
                "user_id": user.telegram_id,
                "tariff_id": tariff.id,
                "tariff_name": tariff.name,
                "promocode": promocode if promocode else None
            }
            
            payment_result = payment_service.create_payment(
                user_id=user.telegram_id,
                tariff_id=tariff.id,
                amount=final_price,
                description=f"Подписка на тариф '{tariff.name}'",
                metadata=metadata
            )
            
            if payment_result:
                confirmation_url = payment_result.get('confirmation_url')
                text = (
                    f"💳 Оплата тарифа '{tariff.name}'\n\n"
                    f"💰 Сумма: {final_price}₽\n"
                    f"⏱️ Длительность: {format_duration(duration_days)}\n\n"
                    f"Для оплаты нажмите кнопку ниже."
                )
                
                markup = types.InlineKeyboardMarkup(row_width=2)
                row = []
                if confirmation_url:
                    row.append(types.InlineKeyboardButton("💳 Оплатить", url=confirmation_url))
                row.append(types.InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_status_{payment_result['payment_id']}"))
                markup.add(*row)
                markup.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment"))
                safe_edit_message_text(bot, call.message.chat.id, call.message.message_id, text, reply_markup=markup)
                logger.info(f"[handle_pay_tariff] Отправлен платежный запрос для пользователя {user.id}. ID платежа: {payment_result.get('payment_id')}")
            else:
                safe_answer_callback(bot, call.id, "❌ Ошибка создания платежа.")
                logger.error(f"[handle_pay_tariff] Ошибка создания платежа для пользователя {user.id}")
        except Exception as e:
            logger.error(f"[handle_pay_tariff] Ошибка при обработке платежа для пользователя {call.from_user.id}: {e}", exc_info=True)
            safe_answer_callback(bot, call.id, "❌ Произошла ошибка при обработке платежа.")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pay_crypto_'))
    def handle_pay_crypto(call):
        """Показывает адрес кошелька и инструкцию для ручной оплаты криптой."""
        logger.info(f"[handle_pay_crypto] callback: {call.data} от {call.from_user.id}")
        parts = call.data.split('_')
        # формат: pay_crypto_<tariff_id>_<final_price>_<duration_days>_<promocode>
        try:
            tariff_id = int(parts[2])
            final_price = float(parts[3])
            duration_days = int(parts[4]) if parts[4] != '0' else None
        except (IndexError, ValueError) as e:
            logger.error(f"[handle_pay_crypto] Ошибка парсинга callback: {e}")
            safe_answer_callback(bot, call.id, "❌ Ошибка.")
            return

        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if not tariff:
                safe_answer_callback(bot, call.id, "❌ Тариф не найден.")
                return

            wallet = Config.CRYPTO_WALLET_ADDRESS
            network = Config.CRYPTO_WALLET_NETWORK
            admin_username = Config.CRYPTO_ADMIN_USERNAME.lstrip('@')

            text = (
                f"🪙 *Оплата криптовалютой — {tariff.name}*\n\n"
                f"💰 Сумма: *{final_price}₽* (в эквиваленте USDT по курсу)\n"
                f"⏱️ Длительность: *{format_duration(duration_days)}*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *Адрес кошелька ({network}):*\n"
                f"`{wallet}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📌 *Инструкция:*\n"
                f"1. Переведите сумму на адрес выше\n"
                f"2. Отправьте скриншот чека: @{admin_username}\n"
                f"3. Подписка активируется после проверки"
            )

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton(
                f"💬 Отправить чек @{admin_username}",
                url=f"https://t.me/{admin_username}"
            ))
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment"))

            safe_edit_message_text(
                bot,
                call.message.chat.id,
                call.message.message_id,
                text,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            safe_answer_callback(bot, call.id)
        except Exception as e:
            logger.error(f"[handle_pay_crypto] Ошибка: {e}", exc_info=True)
            safe_answer_callback(bot, call.id, "❌ Ошибка.")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_payment')
    def cancel_payment(call):
        logger.info(f"[cancel_payment] Получен callback_query 'cancel_payment' от пользователя {call.from_user.id}")
        try:
            safe_edit_message_text(bot, call.message.chat.id, call.message.message_id, "✅ Вы закрыли чек.")
            safe_send_message(bot, call.message.chat.id, "Выберите действие:", reply_markup=main_menu_markup())
            logger.info(f"[cancel_payment] Чек закрыт, отправлено основное меню для {call.from_user.id}")
        except Exception as e:
            logger.error(f"[cancel_payment] Ошибка при отмене платежа для пользователя {call.from_user.id}: {e}", exc_info=True)
            safe_answer_callback(bot, call.id, "❌ Произошла ошибка при отмене платежа.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_sub_'))
    def cancel_subscription(call):
        logger.info(f"[cancel_subscription] Получен callback_query 'cancel_sub_' от пользователя {call.from_user.id}")
        db = SessionLocal()
        try:
            sub_id = int(call.data.split('_')[2])
            sub = db.query(Subscription).filter(Subscription.id == sub_id, Subscription.is_active == True).first()
            if not sub:
                safe_answer_callback(bot, call.id, "Подписка уже неактивна")
                logger.warning(f"[cancel_subscription] Подписка {sub_id} уже неактивна для пользователя {call.from_user.id}")
                return
            sub.is_active = False
            sub.end_date = datetime.utcnow()
            db.commit()
            safe_edit_message_text(bot, call.message.chat.id, call.message.message_id, "❌ Подписка отменена.")
            logger.info(f"[cancel_subscription] Подписка {sub_id} отменена для пользователя {call.from_user.id}")
        except Exception as e:
            db.rollback()
            logger.error(f"[cancel_subscription] Ошибка отмены подписки {sub_id} для пользователя {call.from_user.id}: {e}", exc_info=True)
            safe_answer_callback(bot, call.id, "Ошибка отмены подписки")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('check_status_'))
    def handle_check_status(call):
        logger.info(f"[handle_check_status] Получен callback_query 'check_status_' от пользователя {call.from_user.id}")
        
        # Обновляем активность пользователя
        update_user_activity(call.from_user.id)
        try:
            payment_id = call.data.split('_')[2]

            payment_info = payment_service.get_payment_info(payment_id)
            status = payment_service.check_payment_status(payment_id)

            status_emoji = {
                'pending': '⏳',
                'waiting_for_capture': '⏳',
                'succeeded': '✅',
                'canceled': '❌',
                'failed': '❌'
            }
            status_text = {
                'pending': 'Ожидает оплаты',
                'waiting_for_capture': 'Ожидает подтверждения',
                'succeeded': 'Оплачен',
                'canceled': 'Отменен',
                'failed': 'Ошибка'
            }

            emoji = status_emoji.get(status, '❓')
            text_status = status_text.get(status, status)

            text = (
                f"📊 Статус платежа\n\n"
                f"🆔 ID: {payment_id}\n"
                f"💰 Сумма: {payment_info['amount']} {payment_info['currency']}\n"
                f"📝 Описание: {payment_info.get('description') or ''}\n\n"
                f"Статус: {emoji} {text_status}"
            )

            markup = types.InlineKeyboardMarkup()
            if status in ('pending', 'waiting_for_capture'):
                pay_url = payment_info.get('confirmation_url')
                if pay_url:
                    # Временно отключаем защиту ссылок для тестирования
                    markup.add(types.InlineKeyboardButton("💳 Оплатить", url=pay_url))
                markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data=f"check_status_{payment_id}"))
            elif status == 'succeeded':
                try:
                    payment_service.process_payment_notification(payment_id, 'succeeded')
                except Exception:
                    pass
                
                user = UserService.get_user_by_telegram_id(call.from_user.id)
                if user:
                    # Сбрасываем использование ссылок при успешной оплате
                    LinkProtectionService.reset_user_link_usage(user.telegram_id)
                    
                    
                    db = SessionLocal()
                    try:
                        sub = UserService.get_active_subscription(user.telegram_id)
                        if sub:
                            tariff = db.query(Tariff).filter(Tariff.id == sub.tariff_id).first()
                            till = sub.end_date.strftime('%d.%m.%Y') if sub.end_date.year < 2100 else 'Навсегда'
                            safe_send_message(bot, call.message.chat.id, f"🎉 Подписка активирована!\nТариф: {tariff.name if tariff else '—'}\nДействует до: {till}")
                            
                            # Выдаем доступ к каналу после активации подписки
                            if telegram_channel_service:
                                try:
                                    telegram_channel_service.add_user_to_channel(user.telegram_id)
                                    logger.info(f"Ссылка на канал отправлена пользователю {user.telegram_id} через check_status")
                                except Exception as e:
                                    logger.error(f"Ошибка отправки ссылки на канал пользователю {user.telegram_id}: {e}", exc_info=True)
                            
                            main_menu = main_menu_markup()
                            safe_send_message(bot, call.message.chat.id, "Выберите действие:", reply_markup=main_menu)
                    finally:
                        db.close()
            markup.add(types.InlineKeyboardButton("❌ Закрыть", callback_data="cancel_payment"))

            # Проверяем, изменился ли текст сообщения
            message_key = f"{call.message.chat.id}_{call.message.message_id}"
            cached_text = message_cache.get(message_key)
            
            if cached_text != text:
                try:
                    safe_edit_message_text(bot, call.message.chat.id, call.message.message_id, text, reply_markup=markup)
                    message_cache[message_key] = text  # Кэшируем новый текст
                except Exception as edit_e:
                    logger.error(f"[handle_check_status] Ошибка редактирования сообщения: {edit_e}", exc_info=True)
            else:
                logger.info(f"[handle_check_status] Текст сообщения не изменился, пропускаем редактирование")
            
            # Ограничиваем длину сообщения для callback
            callback_text = f"Статус: {text_status}"[:64]  # Telegram ограничение
            safe_answer_callback(bot, call.id, callback_text if len(callback_text) <= 200 else "✅ Статус обновлен")
            
            logger.info(f"[handle_check_status] Отправлен статус платежа '{payment_id}' для пользователя {call.from_user.id}. Статус: {text_status}")
        except Exception as e:
            logger.error(f"[handle_check_status] Ошибка проверки статуса платежа {payment_id} для пользователя {call.from_user.id}: {e}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "❌ Ошибка. Попробуйте позже.")
            except:
                pass

    @bot.callback_query_handler(func=lambda call: call.data == "link_unavailable")
    def handle_link_unavailable(call):
        """Обработчик для недоступных ссылок"""
        safe_answer_callback(bot, call.id, "❌ Ссылка недоступна. Превышен лимит использования.")
        logger.info(f"[handle_link_unavailable] Пользователь {call.from_user.id} попытался использовать недоступную ссылку")