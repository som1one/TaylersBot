def init_admin_handlers(bot):
    import logging
    from telebot import types
    from config import Config
    from services.user_service import UserService
    from services.broadcast_service import BroadcastService
    from services.statistics_service import StatisticsService
    from services.notification_service import NotificationService
    from database.models import Subscription, Tariff, PromoCode, User, Payment, Ambassador, MarathonMaterial, MarathonPost, ErrorLog
    from database.connection import SessionLocal
    from datetime import datetime, timedelta

    broadcast_service = BroadcastService(bot)
    statistics_service = StatisticsService() # Инициализируем StatisticsService
    admin_promocode_data = {}
    admin_tariff_data = {}

    # Список кнопок админ-панели
    ADMIN_BUTTONS = [
        '📢 Создать рассылку',
        '📊 Статистика',
        '💰 Управление тарифами',
        '🎫 Управление промокодами',
        '🔔 Управление уведомлениями',
        '🎯 Управление материалами марафона',
        '⚠️ Управление ошибками',
        '👥 Администраторы',
        '👥 Амбассадоры',
        '👤 Управление пользователями',
        '❌ Выйти из админ-панели',
        '➕ Добавить админа',
        '➖ Удалить админа',
        '📋 Список админов',
        '➕ Добавить амбассадора',
        '➖ Удалить амбассадора',
        '📋 Список амбассадоров',
        '🔙 Назад',
        '➕ Промокод',
        '🔍 Найти пользователя',
        '🗑️ Удалить пользователя',
        '➕ Добавить материал',
        '📝 Добавить пост',
        '📋 Список материалов',
        '📋 Список постов',
        '📋 Последние ошибки',
        '🔴 Критические ошибки',
        '⚠️ За последние 24ч',
        '✅ Отметить как решенные',
    ]

    # Безопасное редактирование сообщения: корректно работает как с обычными сообщениями, так и с inline
    def safe_edit_message(call, text, reply_markup=None, parse_mode='Markdown'):
        try:
            # inline-сообщение (нет chat/message_id)
            inline_id = getattr(call, 'inline_message_id', None)
            if inline_id:
                bot.edit_message_text(
                    text,
                    inline_message_id=inline_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                return
            # обычное сообщение в чате
            if getattr(call, 'message', None) and call.message:
                bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                return
        except Exception:
            # Падать не даём — отправим новое сообщение
            pass
        # Фоллбек: просто отправим новое сообщение администратору
        try:
            bot.send_message(
                call.from_user.id if getattr(call, 'from_user', None) else call.message.chat.id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception:
            # крайний случай — игнорируем
            pass

    def return_to_main_menu(message):
        """Возвращает пользователя к основному меню"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('🚀 Вступить в бойцовский клуб')
        markup.add('💰 Тарифы', '📱 Моя подписка', 'ℹ️ Помощь')
        bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

    def add_admin_step(message):
        if message.text == '❌ Отмена':
            return_to_main_menu(message)
            return
        try:
            new_id = int(message.text.strip())
            from database.connection import SessionLocal
            from database.models import Admin
            db = SessionLocal()
            try:
                if not db.query(Admin).filter(Admin.telegram_id == new_id).first():
                    db.add(Admin(telegram_id=new_id))
                    db.commit()
                # Обновим кэш конфигурации
                ids = [a.telegram_id for a in db.query(Admin).all()]
                Config.ADMIN_USER_IDS = ids
                bot.send_message(message.chat.id, f"✅ Добавлен администратор: {new_id}")
            finally:
                db.close()
        except Exception:
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID")
        return_to_main_menu(message)

    def remove_admin_step(message):
        if message.text == '❌ Отмена':
            return_to_main_menu(message)
            return
        try:
            rem_id = int(message.text.strip())
            from database.connection import SessionLocal
            from database.models import Admin
            db = SessionLocal()
            try:
                adm = db.query(Admin).filter(Admin.telegram_id == rem_id).first()
                if adm:
                    db.delete(adm)
                    db.commit()
                    ids = [a.telegram_id for a in db.query(Admin).all()]
                    Config.ADMIN_USER_IDS = ids
                    bot.send_message(message.chat.id, f"✅ Удалён администратор: {rem_id}")
                else:
                    bot.send_message(message.chat.id, "⚠️ Такого администратора нет")
            finally:
                db.close()
        except Exception:
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID")
        return_to_main_menu(message)

    def admin_panel(message):
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('📢 Создать рассылку', '📊 Статистика')
        markup.add('💰 Управление тарифами', '🎫 Управление промокодами')
        markup.add('🔔 Управление уведомлениями', '🎯 Управление материалами марафона')
        markup.add('👥 Администраторы', '👥 Амбассадоры', '❌ Выйти из админ-панели')
        bot.send_message(message.chat.id, "🔧 Админ-панель\n\nВыберите действие:", reply_markup=markup)

    @bot.message_handler(commands=['admin'])
    def admin_panel_command(message):
        admin_panel(message)

    @bot.message_handler(func=lambda m: m.from_user.id in Config.ADMIN_USER_IDS and m.text in ADMIN_BUTTONS)
    def admin_panel_buttons(message):
        print(f"[DEBUG_LOG] Received message from admin {message.from_user.id}: '{message.text}' (length: {len(message.text)}, raw: {message.text.encode('utf-8')})")
        
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            print(f"[LOG] Нет доступа к админ-панели: {message.from_user.id}")
            return

        if message.text == '👥 Администраторы':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('➕ Добавить админа', '➖ Удалить админа')
            markup.add('📋 Список админов', '🔙 Назад')
            bot.send_message(message.chat.id, "Управление администраторами:", reply_markup=markup)
            return
        if message.text == '👥 Амбассадоры':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('➕ Добавить амбассадора', '➖ Удалить амбассадора', '📋 Список амбассадоров')
            markup.add('🔙 Назад')
            bot.send_message(message.chat.id, "Управление амбассадорами:", reply_markup=markup)
            return
        if message.text == '➕ Добавить амбассадора':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите Telegram ID пользователя, которого нужно сделать амбассадором:", reply_markup=markup)
            bot.register_next_step_handler(message, process_add_ambassador)
            return
        if message.text == '➖ Удалить амбассадора':
            print("[LOG] Нажата кнопка 'Удалить амбассадора'. Готовимся к регистрации следующего шага.")
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите Telegram ID амбассадора для удаления:", reply_markup=markup)
            bot.register_next_step_handler(message, process_remove_ambassador)
            return
        if message.text == '📋 Список амбассадоров':
            show_ambassadors_list(message)
            return
        if message.text == '🔙 Назад':
            # Проверяем контекст через последнее сообщение пользователя
            # Просто возвращаемся в главное меню админки
            return admin_panel(message)
        if message.text == '📋 Список админов':
            ids = Config.ADMIN_USER_IDS or []
            text = "Текущие администраторы (Telegram ID):\n" + ("\n".join(map(str, ids)) if ids else "—")
            bot.send_message(message.chat.id, text)
            return
        if message.text == '➕ Добавить админа':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите Telegram ID пользователя для добавления в администраторы:", reply_markup=markup)
            bot.register_next_step_handler(message, add_admin_step)
            return
        if message.text == '➖ Удалить админа':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите Telegram ID для удаления из администраторов:", reply_markup=markup)
            bot.register_next_step_handler(message, remove_admin_step)
            return
        if message.text == '➕ Промокод':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите код промокода:", reply_markup=markup)
            bot.register_next_step_handler(message, admin_promocode_code_step)
            return
        if message.text == '📢 Создать рассылку':
            print("[LOG] Запуск этапа ввода текста рассылки")
            bot.send_message(message.chat.id, "📝 Введите текст рассылки:")
            bot.register_next_step_handler(message, broadcast_text_step)
        elif message.text == '📊 Статистика':
            print("[LOG] Запрос статистики")
            
            total_users = statistics_service.get_total_users()
            ambassadors_pending_payout = statistics_service.get_ambassadors_pending_payout()
            total_active_subscriptions = statistics_service.get_total_active_subscriptions()
            purchased_subscriptions = statistics_service.get_purchased_subscriptions_count()
            admin_issued_subscriptions = statistics_service.get_admin_issued_subscriptions_count()
            other_subscriptions = total_active_subscriptions - purchased_subscriptions - admin_issued_subscriptions
            
            new_subs_24h = statistics_service.get_new_active_subscriptions_dynamic(24)
            new_subs_48h = statistics_service.get_new_active_subscriptions_dynamic(48)
            new_subs_7d = statistics_service.get_new_active_subscriptions_dynamic(24 * 7)

            text = (
                "📊 Статистика Бота\n\n"
                f"Общее:\n"
                f"- Всего пользователей: {total_users}\n"
                f"- Амбассадоры (ожидают выплаты): {ambassadors_pending_payout}\n\n"
                f"Подписки:\n"
                f"- Всего активных: {total_active_subscriptions}\n"
                f"- Купленные: {purchased_subscriptions}\n"
                f"- Выданные админом: {admin_issued_subscriptions}\n"
                f"- Другие (старые/неопределенные): {other_subscriptions}\n\n"
                f"Динамика (новые активные подписки):\n"
                f"- За 24 часа: {new_subs_24h}\n"
                f"- За 48 часов: {new_subs_48h}\n"
                f"- За 7 дней: {new_subs_7d}"
            )
            bot.send_message(message.chat.id, text)
        elif message.text == '💰 Управление тарифами':
            print("[LOG] Открытие управления тарифами")
            show_tariffs_management(message)
        elif message.text == '🎫 Управление промокодами':
            print("[LOG] Открытие управления промокодами")
            show_promocodes_management(message)
        elif message.text == '🔔 Управление уведомлениями':
            print("[LOG] Открытие управления уведомлениями")
            show_notifications_menu(message)
        elif message.text == '🎯 Управление материалами марафона':
            show_marathon_materials_menu(message)
        elif message.text == '⚠️ Управление ошибками':
            show_errors_menu(message)
        elif message.text == '🔙 Назад':
            admin_panel(message)
        elif message.text == '❌ Выйти из админ-панели':
            print("[LOG] Выход из админ-панели")
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add('🚀 Вступить в бойцовский клуб')
            markup.add('💰 Тарифы', '📱 Моя подписка', 'ℹ️ Помощь')
            bot.send_message(message.chat.id, "👋 Вы вышли из админ-панели.", reply_markup=markup)

    def broadcast_text_step(message):
        print(f"[LOG] Введён текст рассылки: {message.text}")
        text = message.text
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('➡️ Продолжить без медиа', '❌ Отменить рассылку')
        bot.send_message(message.chat.id, "Прикрепите медиа (фото/видео/документ) или продолжите без медиа:", reply_markup=markup)
        bot.register_next_step_handler(message, broadcast_media_step, text)

    def broadcast_media_step(message, text):
        print(f"[LOG] Этап медиа. Тип: {message.content_type}, Текст: {message.text}")
        if message.text == '❌ Отменить рассылку':
            print("[LOG] Рассылка отменена на этапе медиа")
            bot.send_message(message.chat.id, "❌ Рассылка отменена.", reply_markup=types.ReplyKeyboardRemove())
            return_to_main_menu(message)
            return
        media_type = None
        file_id = None
        if message.content_type == 'photo':
            media_type = 'photo'
            file_id = message.photo[-1].file_id
        elif message.content_type == 'video':
            media_type = 'video'
            file_id = message.video.file_id
        elif message.content_type == 'document':
            media_type = 'document'
            file_id = message.document.file_id
        if message.text == '➡️ Продолжить без медиа' or not file_id:
            print("[LOG] Продолжение без медиа")
            media_type = None
            file_id = None
        print(f"[LOG] Предпросмотр рассылки. text={text}, media_type={media_type}, file_id={file_id}")
        # --- Предпросмотр рассылки ---
        preview_markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        preview_markup.add('✅ Отправить рассылку', '❌ Отменить рассылку')
        if media_type == 'photo' and file_id:
            bot.send_photo(message.chat.id, file_id, caption=f"[ПРЕДПРОСМОТР]\n{text}", reply_markup=preview_markup)
        elif media_type == 'video' and file_id:
            bot.send_video(message.chat.id, file_id, caption=f"[ПРЕДПРОСМОТР]\n{text}", reply_markup=preview_markup)
        elif media_type == 'document' and file_id:
            bot.send_document(message.chat.id, file_id, caption=f"[ПРЕДПРОСМОТР]\n{text}", reply_markup=preview_markup)
        else:
            bot.send_message(message.chat.id, f"[ПРЕДПРОСМОТР]\n{text}", reply_markup=preview_markup)
        bot.register_next_step_handler(message, broadcast_confirm_step, text, media_type, file_id)

    def broadcast_confirm_step(message, text, media_type, file_id):
        print(f"[LOG] Подтверждение: {message.text}")
        if message.text == '❌ Отменить рассылку':
            print("[LOG] Рассылка отменена на этапе подтверждения")
            bot.send_message(message.chat.id, "❌ Рассылка отменена.", reply_markup=types.ReplyKeyboardRemove())
            return_to_main_menu(message)
            return
        if message.text == '✅ Отправить рассылку':
            print(f"[LOG] Отправка рассылки: text={text}, media_type={media_type}, file_id={file_id}")
            message_data = {
                'message': text,
                'media_type': media_type,
                'media_file_id': file_id
            }
            bot.send_message(message.chat.id, "📤 Отправляю рассылку...", reply_markup=types.ReplyKeyboardRemove())
            bot.send_chat_action(message.chat.id, 'typing')
            import threading
            threading.Thread(target=broadcast_service.send_direct_broadcast, args=(message_data,)).start()
            print("[LOG] Рассылка отправлена!")
            bot.send_message(message.chat.id, "✅ Рассылка успешно отправлена!")
            return_to_main_menu(message)

    def show_tariffs_management(message):
        print(f"[LOG] Открытие меню управления тарифами для {message.from_user.id}")
        db = SessionLocal()
        try:
            tariffs = db.query(Tariff).order_by(Tariff.name).all()
            markup = types.InlineKeyboardMarkup()
            for tariff in tariffs:
                status = "✅" if tariff.is_active else "❌"
                tariff_text = f"{status} {tariff.name} - {tariff.price}₽"
                markup.add(types.InlineKeyboardButton(tariff_text, callback_data=f"edit_tariff_{tariff.id}"))
            markup.add(types.InlineKeyboardButton("➕ Добавить тариф", callback_data="add_tariff"))
            markup.add(types.InlineKeyboardButton("🔙 Назад в админ-панель", callback_data="back_to_admin"))
            bot.send_message(message.chat.id, "💰 Управление тарифами:", reply_markup=markup)
        finally:
            db.close()

    def show_promocodes_management(message):
        print(f"[LOG] Открытие меню управления промокодами для {message.from_user.id}")
        # Проверяем и деактивируем просроченные промокоды
        check_and_deactivate_expired_promocodes()
        db = SessionLocal()
        try:
            promocodes = db.query(PromoCode).order_by(PromoCode.created_at.desc()).all()
            markup = types.InlineKeyboardMarkup()
            for promo in promocodes:
                status = "✅" if promo.is_active else "❌"
                if promo.expires_at and promo.expires_at < datetime.utcnow():
                    status = "⏰"
                promo_text = f"{status} {promo.code}"
                if promo.discount_percent:
                    promo_text += f" (-{promo.discount_percent}%)"
                elif promo.is_free:
                    if promo.duration_days:
                        promo_text += f" (бесплатно {promo.duration_days}д)"
                    else:
                        promo_text += " (бесплатно навсегда)"
                markup.add(types.InlineKeyboardButton(promo_text, callback_data=f"edit_promo_{promo.id}"))
            markup.add(types.InlineKeyboardButton("➕ Добавить промокод", callback_data="add_promocode"))
            markup.add(types.InlineKeyboardButton("🔙 Назад в админ-панель", callback_data="back_to_admin"))
            bot.send_message(message.chat.id, "🎫 Управление промокодами:", reply_markup=markup)
        finally:
            db.close()

    def check_and_deactivate_expired_promocodes():
        """Проверяет и деактивирует просроченные промокоды"""
        db = SessionLocal()
        try:
            expired_promos = db.query(PromoCode).filter(
                PromoCode.is_active == True,
                PromoCode.expires_at < datetime.utcnow()
            ).all()
            for promo in expired_promos:
                promo.is_active = False
            if expired_promos:
                db.commit()
                print(f"[LOG] Деактивировано {len(expired_promos)} просроченных промокодов")
        except Exception as e:
            print(f"[LOG] Ошибка при деактивации промокодов: {e}")
            db.rollback()
        finally:
            db.close()

    def admin_promocode_code_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        code = message.text.strip().upper()
        # Проверка на дубликаты
        db = SessionLocal()
        try:
            existing_promo = db.query(PromoCode).filter(PromoCode.code == code).first()
            if existing_promo:
                bot.send_message(message.chat.id, f"❌ Промокод '{code}' уже существует! Попробуйте другой код:")
                bot.register_next_step_handler(message, admin_promocode_code_step)
                return
        finally:
            db.close()
        admin_promocode_data[message.chat.id] = {'code': code}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('Скидка %', 'Бесплатно', '❌ Отмена')
        bot.send_message(message.chat.id, "Выберите тип промокода:", reply_markup=markup)
        bot.register_next_step_handler(message, admin_promocode_type_step)

    def admin_promocode_type_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        if message.text == 'Скидка %':
            admin_promocode_data[message.chat.id]['is_free'] = False
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите процент скидки (1-100):", reply_markup=markup)
            bot.register_next_step_handler(message, admin_promocode_discount_step)
        elif message.text == 'Бесплатно':
            admin_promocode_data[message.chat.id]['is_free'] = True
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('В днях', 'В месяцах', 'Навсегда', '❌ Отмена')
            bot.send_message(message.chat.id, "Выберите тип длительности бесплатного периода:", reply_markup=markup)
            bot.register_next_step_handler(message, admin_promocode_free_duration_type_step)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, выберите вариант с клавиатуры.")
            bot.register_next_step_handler(message, admin_promocode_type_step)

    def admin_promocode_discount_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        try:
            percent = int(message.text.strip())
            if not (1 <= percent <= 100):
                raise ValueError
        except ValueError:
            bot.send_message(message.chat.id, "Введите число от 1 до 100:")
            bot.register_next_step_handler(message, admin_promocode_discount_step)
            return
        admin_promocode_data[message.chat.id]['discount_percent'] = percent
        admin_promocode_data[message.chat.id]['duration_days'] = None
        admin_promocode_next_common(message)

    def admin_promocode_free_duration_type_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        if message.text == 'Навсегда':
            admin_promocode_data[message.chat.id]['discount_percent'] = None
            admin_promocode_data[message.chat.id]['duration_days'] = None
            admin_promocode_next_common(message)
            return
        elif message.text == 'В месяцах':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите длительность бесплатного периода в месяцах (например: 3):", reply_markup=markup)
            bot.register_next_step_handler(message, admin_promocode_free_months_step)
            return
        elif message.text == 'В днях':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "Введите длительность бесплатного периода в днях (например: 30):", reply_markup=markup)
            bot.register_next_step_handler(message, admin_promocode_free_days_step)
            return
        else:
            bot.send_message(message.chat.id, "Пожалуйста, выберите вариант с клавиатуры.")
            bot.register_next_step_handler(message, admin_promocode_free_duration_type_step)

    def admin_promocode_free_days_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        try:
            days = int(message.text.strip())
            if not (1 <= days <= 3650):
                raise ValueError
        except ValueError:
            bot.send_message(message.chat.id, "Введите число дней (1-3650):")
            bot.register_next_step_handler(message, admin_promocode_free_days_step)
            return
        admin_promocode_data[message.chat.id]['discount_percent'] = None
        admin_promocode_data[message.chat.id]['duration_days'] = days
        admin_promocode_next_common(message)

    def admin_promocode_free_months_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        try:
            months = int(message.text.strip())
            if not (1 <= months <= 120):
                raise ValueError
        except ValueError:
            bot.send_message(message.chat.id, "Введите число месяцев (1-120):")
            bot.register_next_step_handler(message, admin_promocode_free_months_step)
            return
        admin_promocode_data[message.chat.id]['discount_percent'] = None
        admin_promocode_data[message.chat.id]['duration_days'] = months * 30
        admin_promocode_next_common(message)

    def admin_promocode_next_common(message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(message.chat.id, "Введите дату окончания действия промокода (ГГГГ-ММ-ДД) или '-' для бессрочного:", reply_markup=markup)
        bot.register_next_step_handler(message, admin_promocode_expiry_step)

    def admin_promocode_expiry_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        expires_at = None
        if message.text.strip() != '-':
            try:
                expires_at = datetime.strptime(message.text.strip(), '%Y-%m-%d')
            except Exception:
                bot.send_message(message.chat.id, "Введите дату в формате ГГГГ-ММ-ДД или '-' для бессрочного:")
                bot.register_next_step_handler(message, admin_promocode_expiry_step)
                return
        admin_promocode_data[message.chat.id]['expires_at'] = expires_at
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(message.chat.id, "Введите лимит использования (число) или '-' для безлимитного:", reply_markup=markup)
        bot.register_next_step_handler(message, admin_promocode_limit_step)

    def admin_promocode_limit_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        usage_limit = None
        if message.text.strip() != '-':
            try:
                usage_limit = int(message.text.strip())
                if usage_limit < 1:
                    raise ValueError
            except Exception:
                bot.send_message(message.chat.id, "Введите положительное число или '-' для безлимитного:")
                bot.register_next_step_handler(message, admin_promocode_limit_step)
                return
        admin_promocode_data[message.chat.id]['usage_limit'] = usage_limit
        admin_promocode_confirm(message)

    def admin_promocode_confirm(message):
        data = admin_promocode_data[message.chat.id]
        text = f"Промокод: {data['code']}\n"
        if data['discount_percent']:
            text += f"Скидка: {data['discount_percent']}%\n"
        if data['is_free']:
            if data['duration_days'] is None:
                text += f"Бесплатно на: Навсегда\n"
            else:
                text += f"Бесплатно на: {data['duration_days']} дней\n"
        if data['expires_at']:
            text += f"Действует до: {data['expires_at'].strftime('%Y-%m-%d')}\n"
        if data['usage_limit']:
            text += f"Лимит использований: {data['usage_limit']}\n"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('✅ Создать', '❌ Отмена')
        bot.send_message(message.chat.id, text + "\nПодтвердите создание промокода:", reply_markup=markup)
        bot.register_next_step_handler(message, admin_promocode_save_step)

    def admin_promocode_save_step(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание промокода отменено.")
            return_to_main_menu(message)
            return
        if message.text == '✅ Создать':
            data = admin_promocode_data[message.chat.id]
            db = SessionLocal()
            try:
                promo = PromoCode(
                    code=data['code'],
                    discount_percent=data['discount_percent'],
                    is_free=data.get('is_free', False),
                    duration_days=data['duration_days'],
                    expires_at=data['expires_at'],
                    is_active=True,
                    usage_limit=data['usage_limit'],
                    usage_count=0
                )
                db.add(promo)
                db.commit()
                bot.send_message(message.chat.id, f"✅ Промокод {data['code']} успешно создан!")
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Ошибка при создании промокода: {e}")
                db.rollback()
            finally:
                db.close()
            admin_promocode_data.pop(message.chat.id, None)
            return_to_main_menu(message)

    # Обработчики для управления промокодами
    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_promo_') or call.data == 'add_promocode')
    def handle_promocode_admin_callback(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        if call.data == 'add_promocode':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(call.message.chat.id, "Введите код промокода:", reply_markup=markup)
            bot.register_next_step_handler(call.message, admin_promocode_code_step)
        elif call.data.startswith('edit_promo_'):
            promo_id = int(call.data.split('_')[-1])
            db = SessionLocal()
            try:
                promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
                if not promo:
                    bot.answer_callback_query(call.id, "Промокод не найден.")
                    return
                status = "Активен" if promo.is_active else "Неактивен"
                if promo.expires_at and promo.expires_at < datetime.utcnow():
                    status = "Просрочен"
                text = f"🎫 Промокод: {promo.code}\n"
                if promo.discount_percent:
                    text += f"Скидка: {promo.discount_percent}%\n"
                elif promo.is_free:
                    if promo.duration_days:
                        text += f"Бесплатно на: {promo.duration_days} дней\n"
                    else:
                        text += f"Бесплатно на: Навсегда\n"
                text += f"Использований: {promo.usage_count}"
                if promo.usage_limit:
                    text += f"/{promo.usage_limit}"
                text += f"\nСтатус: {status}"
                if promo.expires_at:
                    text += f"\nДействует до: {promo.expires_at.strftime('%Y-%m-%d')}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔄 Изменить статус", callback_data=f"toggle_promo_{promo_id}"))
                markup.add(types.InlineKeyboardButton("❌ Удалить промокод", callback_data=f"delete_promo_{promo_id}"))
                markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="manage_promocodes"))
                safe_edit_message(call, text, reply_markup=markup)
            finally:
                db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_promo_'))
    def toggle_promocode_status(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        promo_id = int(call.data.split('_')[-1])
        db = SessionLocal()
        try:
            promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
            if not promo:
                bot.answer_callback_query(call.id, "Промокод не найден.")
                return
            promo.is_active = not promo.is_active
            db.commit()

            # Обновляем текущее сообщение с новым статусом
            status = "Активен" if promo.is_active else "Неактивен"
            if promo.expires_at and promo.expires_at < datetime.utcnow():
                status = "Просрочен"
            text = f"🎫 Промокод: {promo.code}\n"
            if promo.discount_percent:
                text += f"Скидка: {promo.discount_percent}%\n"
            elif promo.is_free:
                if promo.duration_days:
                    text += f"Бесплатно на: {promo.duration_days} дней\n"
                else:
                    text += f"Бесплатно на: Навсегда\n"
            text += f"Использований: {promo.usage_count}"
            if promo.usage_limit:
                text += f"/{promo.usage_limit}"
            text += f"\nСтатус: {status}"
            if promo.expires_at:
                text += f"\nДействует до: {promo.expires_at.strftime('%Y-%m-%d')}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔄 Изменить статус", callback_data=f"toggle_promo_{promo_id}"))
            markup.add(types.InlineKeyboardButton("❌ Удалить промокод", callback_data=f"delete_promo_{promo_id}"))
            markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="manage_promocodes"))
            safe_edit_message(call, text, reply_markup=markup)
            bot.answer_callback_query(call.id, f"Промокод {'активирован' if promo.is_active else 'деактивирован'}")
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")
            db.rollback()
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('delete_promo_'))
    def delete_promocode_prompt(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        promo_id = int(call.data.split('_')[-1])
        db = SessionLocal()
        try:
            promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
            if not promo:
                bot.answer_callback_query(call.id, "Промокод не найден.")
                return
            text = f"⚠️ Вы уверены, что хотите удалить промокод '{promo.code}'?\n\nЭто действие нельзя отменить!"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_promo_{promo_id}"))
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"edit_promo_{promo_id}"))
            safe_edit_message(call, text, reply_markup=markup)
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_promo_'))
    def confirm_delete_promocode(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        promo_id = int(call.data.split('_')[-1])
        db = SessionLocal()
        try:
            promo = db.query(PromoCode).filter(PromoCode.id == promo_id).first()
            if not promo:
                bot.answer_callback_query(call.id, "Промокод не найден.")
                return
            promo_code = promo.code
            db.delete(promo)
            db.commit()
            safe_edit_message(call, f"✅ Промокод '{promo_code}' успешно удален!")
            # Возвращаемся к списку промокодов
            msg = type('msg', (), {'chat': call.message.chat, 'from_user': call.from_user})()
            show_promocodes_management(msg)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")
            db.rollback()
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data == 'manage_promocodes')
    def manage_promocodes_back(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        msg = type('msg', (), {'chat': call.message.chat, 'from_user': call.from_user})()
        show_promocodes_management(msg)

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_admin')
    def back_to_admin_panel(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        msg = type('msg', (), {'chat': call.message.chat, 'from_user': call.from_user})()
        admin_panel(msg)

    @bot.callback_query_handler(func=lambda call: call.data == 'back_to_notifications')
    def back_to_notifications(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "Нет доступа.")
            return
        msg = type('msg', (), {'chat': call.message.chat, 'from_user': call.from_user})()
        show_notifications_menu(msg)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_tariff_'))
    def edit_tariff(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if not tariff:
                bot.answer_callback_query(call.id, "❌ Тариф не найден")
                return

            text = (
                f"📝 Редактирование тарифа: {tariff.name}\n\n"
                f"💰 Текущая цена: {tariff.price}₽\n"
                f"⏱️ Длительность: {tariff.duration_days} дней\n"
                f"📝 Описание: {tariff.description or 'Не указано'}\n"
                f"✅ Статус: {'Активен' if tariff.is_active else 'Неактивен'}\n"
                f"⭐️ Главный тариф: {'Да' if tariff.is_main else 'Нет'}\n\n"
                f"Выберите действие:"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            main_btn_text = "⭐ Убрать из главных" if tariff.is_main else "⭐️ Сделать главным"
            markup.add(
                types.InlineKeyboardButton("💰 Изменить цену", callback_data=f"edit_price_{tariff.id}"),
                types.InlineKeyboardButton("⏱️ Изменить длительность", callback_data=f"edit_duration_{tariff.id}"),
                types.InlineKeyboardButton("📝 Изменить описание", callback_data=f"edit_description_{tariff.id}"),
                types.InlineKeyboardButton("✅/❌ Переключить статус", callback_data=f"toggle_tariff_{tariff.id}"),
                types.InlineKeyboardButton(main_btn_text, callback_data=f"toggle_main_tariff_{tariff.id}"),
                types.InlineKeyboardButton("🗑️ Удалить тариф", callback_data=f"delete_tariff_{tariff.id}"),
                types.InlineKeyboardButton("🔙 Назад", callback_data="manage_tariffs")
            )

            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_price_'))
    def edit_tariff_price(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(call.message.chat.id, "💰 Введите новую цену тарифа (в рублях):", reply_markup=markup)
        bot.register_next_step_handler(call.message, save_tariff_price, tariff_id)

    def save_tariff_price(message, tariff_id):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Изменение цены отменено.")
            return_to_main_menu(message)
            return

        try:
            new_price = float(message.text.strip())
            if new_price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной. Попробуйте снова:")
                bot.register_next_step_handler(message, save_tariff_price, tariff_id)
                return

            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if tariff:
                    tariff.price = new_price
                    db.commit()
                    bot.send_message(message.chat.id, f"✅ Цена тарифа '{tariff.name}' изменена на {new_price}₽")
                    # Возвращаемся к редактированию тарифа
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К редактированию тарифа", callback_data=f"edit_tariff_{tariff_id}"))
                    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
                else:
                    bot.send_message(message.chat.id, "❌ Тариф не найден")
                    return_to_main_menu(message)
            finally:
                db.close()
        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная цена. Введите число:")
            bot.register_next_step_handler(message, save_tariff_price, tariff_id)
            return

        return_to_main_menu(message)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_duration_'))
    def edit_tariff_duration(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('В днях', 'В месяцах', 'Навсегда', '❌ Отмена')
        bot.send_message(call.message.chat.id, "⏱️ Выберите тип длительности:", reply_markup=markup)
        bot.register_next_step_handler(call.message, edit_tariff_duration_type, tariff_id)

    def edit_tariff_duration_type(message, tariff_id):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Изменение длительности отменено.")
            return_to_main_menu(message)
            return

        if message.text == 'В днях':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "⏱️ Введите длительность в днях:", reply_markup=markup)
            bot.register_next_step_handler(message, save_tariff_duration_days, tariff_id)
        elif message.text == 'В месяцах':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "⏱️ Введите длительность в месяцах:", reply_markup=markup)
            bot.register_next_step_handler(message, save_tariff_duration_months, tariff_id)
        elif message.text == 'Навсегда':
            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if tariff:
                    tariff.duration_days = 36500  # 100 лет = навсегда
                    db.commit()
                    bot.send_message(message.chat.id, f"✅ Длительность тарифа '{tariff.name}' изменена на 'Навсегда'")
                    # Возвращаемся к редактированию тарифа
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К редактированию тарифа", callback_data=f"edit_tariff_{tariff_id}"))
                    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
                else:
                    bot.send_message(message.chat.id, "❌ Тариф не найден")
                    return_to_main_menu(message)
            finally:
                db.close()
            return_to_main_menu(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, выберите вариант с клавиатуры.")
            bot.register_next_step_handler(message, edit_tariff_duration_type, tariff_id)

    def save_tariff_duration_days(message, tariff_id):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Изменение длительности отменено.")
            return_to_main_menu(message)
            return

        try:
            days = int(message.text.strip())
            if days <= 0:
                bot.send_message(message.chat.id, "❌ Длительность должна быть положительной. Попробуйте снова:")
                bot.register_next_step_handler(message, save_tariff_duration_days, tariff_id)
                return

            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if tariff:
                    tariff.duration_days = days
                    db.commit()
                    bot.send_message(message.chat.id, f"✅ Длительность тарифа '{tariff.name}' изменена на {days} дней")
                    # Возвращаемся к редактированию тарифа
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К редактированию тарифа", callback_data=f"edit_tariff_{tariff_id}"))
                    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
                else:
                    bot.send_message(message.chat.id, "❌ Тариф не найден")
                    return_to_main_menu(message)
            finally:
                db.close()
        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная длительность. Введите число:")
            bot.register_next_step_handler(message, save_tariff_duration_days, tariff_id)
            return

    def save_tariff_duration_months(message, tariff_id):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Изменение длительности отменено.")
            return_to_main_menu(message)
            return

        try:
            months = int(message.text.strip())
            if months <= 0:
                bot.send_message(message.chat.id, "❌ Длительность должна быть положительной. Попробуйте снова:")
                bot.register_next_step_handler(message, save_tariff_duration_months, tariff_id)
                return

            days = months * 30  # Примерно 30 дней в месяце

            db = SessionLocal()
            try:
                tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
                if tariff:
                    tariff.duration_days = days
                    db.commit()
                    bot.send_message(message.chat.id, f"✅ Длительность тарифа '{tariff.name}' изменена на {months} месяцев ({days} дней)")
                    # Возвращаемся к редактированию тарифа
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К редактированию тарифа", callback_data=f"edit_tariff_{tariff_id}"))
                    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
                else:
                    bot.send_message(message.chat.id, "❌ Тариф не найден")
                    return_to_main_menu(message)
            finally:
                db.close()
        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная длительность. Введите число:")
            bot.register_next_step_handler(message, save_tariff_duration_months, tariff_id)
            return

    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_description_'))
    def edit_tariff_description(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(call.message.chat.id, "📝 Введите новое описание тарифа (или 'Убрать' для удаления):", reply_markup=markup)
        bot.register_next_step_handler(call.message, save_tariff_description, tariff_id)

    def save_tariff_description(message, tariff_id):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Изменение описания отменено.")
            return_to_main_menu(message)
            return

        new_description = None if message.text.strip() == 'Убрать' else message.text.strip()

        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if tariff:
                tariff.description = new_description
                db.commit()
                if new_description:
                    bot.send_message(message.chat.id, f"✅ Описание тарифа '{tariff.name}' изменено")
                else:
                    bot.send_message(message.chat.id, f"✅ Описание тарифа '{tariff.name}' удалено")
                # Возвращаемся к редактированию тарифа
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 К редактированию тарифа", callback_data=f"edit_tariff_{tariff_id}"))
                bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)
            else:
                bot.send_message(message.chat.id, "❌ Тариф не найден")
                return_to_main_menu(message)
        finally:
            db.close()

        return_to_main_menu(message)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_tariff_'))
    def toggle_tariff_status(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if tariff:
                tariff.is_active = not tariff.is_active
                db.commit()
                status = "активирован" if tariff.is_active else "деактивирован"
                bot.answer_callback_query(call.id, f"✅ Тариф '{tariff.name}' {status}")
                # Обновляем сообщение
                edit_tariff(call)
            else:
                bot.answer_callback_query(call.id, "❌ Тариф не найден")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_main_tariff_'))
    def toggle_main_tariff(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if tariff:
                if not tariff.is_main:
                    # Убираем флаг у всех остальных тарифов
                    db.query(Tariff).update({"is_main": False})
                    tariff.is_main = True
                    db.commit()
                    bot.answer_callback_query(call.id, f"✅ Тариф '{tariff.name}' сделан главным")
                else:
                    tariff.is_main = False
                    db.commit()
                    bot.answer_callback_query(call.id, f"✅ Тариф '{tariff.name}' убран из главных")
                
                # Обновляем меню
                edit_tariff(call)
            else:
                bot.answer_callback_query(call.id, "❌ Тариф не найден")
        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('delete_tariff_'))
    def delete_tariff_prompt(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if tariff:
                text = f"⚠️ Вы уверены, что хотите удалить тариф '{tariff.name}'?\n\nЭто действие нельзя отменить!"
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("🗑️ Да, удалить", callback_data=f"confirm_delete_tariff_{tariff.id}"),
                    types.InlineKeyboardButton("❌ Отмена", callback_data=f"edit_tariff_{tariff.id}")
                )
                safe_edit_message(call, text, reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, "❌ Тариф не найден")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_tariff_'))
    def confirm_delete_tariff(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        tariff_id = int(call.data.split('_')[-1])  # Берем последний элемент - ID тарифа
        db = SessionLocal()
        try:
            tariff = db.query(Tariff).filter(Tariff.id == tariff_id).first()
            if tariff:
                # Проверяем, есть ли активные подписки на этот тариф
                from database.models import Subscription
                active_subscriptions = db.query(Subscription).filter(
                    Subscription.tariff_id == tariff_id,
                    Subscription.is_active == True
                ).count()

                if active_subscriptions > 0:
                    # Вместо удаления деактивируем тариф
                    tariff.is_active = False
                    db.commit()
                    safe_edit_message(call, f"⚠️ Тариф '{tariff.name}' деактивирован (нельзя удалить с {active_subscriptions} активными подписками)")
                    # Возвращаемся к управлению тарифами для обновления статуса
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К управлению тарифами", callback_data="manage_tariffs"))
                    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)
                else:
                    # Если подписок нет - можно удалить
                    tariff_name = tariff.name
                    db.delete(tariff)
                    db.commit()
                    safe_edit_message(call, f"✅ Тариф '{tariff_name}' удален")

                    # Возвращаемся к управлению тарифами
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 К управлению тарифами", callback_data="manage_tariffs"))
                    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, "❌ Тариф не найден")
        except Exception as e:
            # Ограничиваем длину сообщения об ошибке
            error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {error_msg}")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data == 'manage_tariffs')
    def manage_tariffs_back(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        show_tariffs_management(call.message)

    @bot.callback_query_handler(func=lambda call: call.data == 'add_tariff')
    def add_tariff_start(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(call.message.chat.id, "📝 Введите название нового тарифа:", reply_markup=markup)
        bot.register_next_step_handler(call.message, add_tariff_name)

    def add_tariff_name(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        if not message.text.strip():
            bot.send_message(message.chat.id, "❌ Название не может быть пустым. Попробуйте снова:")
            bot.register_next_step_handler(message, add_tariff_name)
            return

        # Сохраняем название и запрашиваем цену
        admin_tariff_data[message.chat.id] = {'name': message.text.strip()}
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(message.chat.id, "💰 Введите цену тарифа (в рублях):", reply_markup=markup)
        bot.register_next_step_handler(message, add_tariff_price)

    def add_tariff_price(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        try:
            price = float(message.text.strip())
            if price < 0:
                bot.send_message(message.chat.id, "❌ Цена не может быть отрицательной. Попробуйте снова:")
                bot.register_next_step_handler(message, add_tariff_price)
                return

            admin_tariff_data[message.chat.id]['price'] = price

            # Запрашиваем длительность
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('В днях', 'В месяцах', 'Навсегда', '❌ Отмена')
            bot.send_message(message.chat.id, "⏱️ Выберите тип длительности:", reply_markup=markup)
            bot.register_next_step_handler(message, add_tariff_duration_type)

        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная цена. Введите число:")
            bot.register_next_step_handler(message, add_tariff_price)

    def add_tariff_duration_type(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        if message.text == 'В днях':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "⏱️ Введите длительность в днях:", reply_markup=markup)
            bot.register_next_step_handler(message, add_tariff_duration_days)
        elif message.text == 'В месяцах':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена')
            bot.send_message(message.chat.id, "⏱️ Введите длительность в месяцах:", reply_markup=markup)
            bot.register_next_step_handler(message, add_tariff_duration_months)
        elif message.text == 'Навсегда':
            admin_tariff_data[message.chat.id]['duration_days'] = 36500
            add_tariff_description_step(message)
        else:
            bot.send_message(message.chat.id, "Пожалуйста, выберите вариант с клавиатуры.")
            bot.register_next_step_handler(message, add_tariff_duration_type)

    def add_tariff_duration_days(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        try:
            days = int(message.text.strip())
            if days <= 0:
                bot.send_message(message.chat.id, "❌ Длительность должна быть положительной. Попробуйте снова:")
                bot.register_next_step_handler(message, add_tariff_duration_days)
                return

            admin_tariff_data[message.chat.id]['duration_days'] = days
            add_tariff_description_step(message)

        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная длительность. Введите число:")
            bot.register_next_step_handler(message, add_tariff_duration_days)

    def add_tariff_duration_months(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        try:
            months = int(message.text.strip())
            if months <= 0:
                bot.send_message(message.chat.id, "❌ Длительность должна быть положительной. Попробуйте снова:")
                bot.register_next_step_handler(message, add_tariff_duration_months)
                return

            days = months * 30  # Примерно 30 дней в месяце
            admin_tariff_data[message.chat.id]['duration_days'] = days
            add_tariff_description_step(message)

        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректная длительность. Введите число:")
            bot.register_next_step_handler(message, add_tariff_duration_months)

    def add_tariff_description_step(message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('Пропустить', '❌ Отмена')
        bot.send_message(message.chat.id, "📝 Введите описание тарифа (или 'Пропустить'):", reply_markup=markup)
        bot.register_next_step_handler(message, add_tariff_confirm)

    def add_tariff_confirm(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Создание тарифа отменено.")
            return_to_main_menu(message)
            return

        if message.text != 'Пропустить':
            admin_tariff_data[message.chat.id]['description'] = message.text.strip()
        else:
            admin_tariff_data[message.chat.id]['description'] = None

        # Показываем итог для подтверждения
        data = admin_tariff_data[message.chat.id]
        duration_text = "Навсегда" if data['duration_days'] >= 36500 else f"{data['duration_days']} дней"

        text = (
            f"📝 Подтверждение создания тарифа:\n\n"
            f"📦 Название: {data['name']}\n"
            f"💰 Цена: {data['price']}₽\n"
            f"⏱️ Длительность: {duration_text}\n"
            f"📝 Описание: {data['description'] or 'Не указано'}\n\n"
            f"Создать тариф?"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Создать", callback_data="confirm_add_tariff"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_tariff")
        )

        bot.send_message(message.chat.id, text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == 'confirm_add_tariff')
    def confirm_add_tariff(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        user_id = call.from_user.id
        if user_id not in admin_tariff_data:
            bot.answer_callback_query(call.id, "❌ Данные тарифа не найдены")
            return

        data = admin_tariff_data[user_id]

        db = SessionLocal()
        try:
            new_tariff = Tariff(
                name=data['name'],
                price=data['price'],
                duration_days=data['duration_days'],
                description=data['description'],
                is_active=True
            )
            db.add(new_tariff)
            db.commit()

            bot.edit_message_text(f"✅ Тариф '{data['name']}' успешно создан!", call.message.chat.id, call.message.message_id)

            # Очищаем данные
            if user_id in admin_tariff_data:
                del admin_tariff_data[user_id]

            # Возвращаемся к управлению тарифами
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 К управлению тарифами", callback_data="manage_tariffs"))
            bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка создания: {e}")
            db.rollback()
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_add_tariff')
    def cancel_add_tariff(call):
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        user_id = call.from_user.id
        if user_id in admin_tariff_data:
            del admin_tariff_data[user_id]

        bot.edit_message_text("❌ Создание тарифа отменено.", call.message.chat.id, call.message.message_id)

        # Возвращаемся к управлению тарифами
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 К управлению тарифами", callback_data="manage_tariffs"))
        bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=markup)

    def process_add_ambassador(message):
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Добавление амбассадора отменено.")
            return_to_main_menu(message)
            return
        try:
            user_id_to_make_ambassador = int(message.text.strip())
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == user_id_to_make_ambassador).first()
                if not user:
                    bot.send_message(message.chat.id, "❌ Пользователь с таким Telegram ID не найден. Пожалуйста, убедитесь, что пользователь уже взаимодействовал с ботом.")
                    return
                
                if user.is_ambassador:
                    bot.send_message(message.chat.id, f"⚠️ Пользователь {user.username or user.telegram_id} уже является амбассадором.")
                else:
                    if statistics_service.make_user_ambassador(user.telegram_id):
                        db.refresh(user) # Обновляем объект user, чтобы получить ambassador_code
                        # Генерируем реферальную ссылку
                        bot_username = bot.get_me().username
                        referral_link = f"https://t.me/{bot_username}?start={user.ambassador_code}"
                        bot.send_message(message.chat.id, f"✅ Пользователь {user.username or user.telegram_id} успешно стал амбассадором!\nЕго реферальная ссылка: {referral_link}")
                    else:
                        bot.send_message(message.chat.id, "❌ Ошибка при добавлении амбассадора.")
            finally:
                db.close()
        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID. Введите число.")
        finally:
            return_to_main_menu(message)

    def process_remove_ambassador(message):
        print(f"[LOG] Запущена функция process_remove_ambassador для пользователя {message.from_user.id}")
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Удаление амбассадора отменено.")
            return_to_main_menu(message)
            return
        try:
            user_id_to_remove_ambassador = int(message.text.strip())
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == user_id_to_remove_ambassador).first()
                if not user:
                    bot.send_message(message.chat.id, "❌ Пользователь с таким Telegram ID не найден.")
                    return
                
                if not user.is_ambassador:
                    bot.send_message(message.chat.id, f"⚠️ Пользователь {user.username or user.telegram_id} не является амбассадором.")
                    return

                print(f"[LOG] Попытка удалить амбассадора с ID: {user.id} (Telegram ID: {user.telegram_id})")
                if statistics_service.remove_user_ambassador(user.telegram_id):
                    print(f"[LOG] Амбассадор {user.id} успешно удален через StatisticsService.")
                    bot.send_message(message.chat.id, f"✅ Амбассадор {user.username or user.telegram_id} успешно удален.")
                else:
                    print(f"[LOG] Ошибка: StatisticsService.remove_user_ambassador вернул False для ID {user.id}.")
                    bot.send_message(message.chat.id, "❌ Ошибка при удалении амбассадора.")
            finally:
                db.close()
        except ValueError:
            print(f"[LOG] Ошибка ValueError при удалении амбассадора: Некорректный Telegram ID '{message.text}'.")
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID. Введите число.")
        except Exception as e:
            print(f"[LOG] Неожиданная ошибка при удалении амбассадора: {e}")
            bot.send_message(message.chat.id, f"❌ Произошла непредвиденная ошибка: {e}")
        finally:
            return_to_main_menu(message)

    def show_ambassadors_list(message):
        print("[LOG] Запрос списка амбассадоров")
        ambassadors_data = statistics_service.get_ambassadors_list()
        
        if not ambassadors_data:
            bot.send_message(message.chat.id, "Список амбассадоров пуст.")
            return

        text = "👑 Список Амбассадоров:\n\n"
        bot_username = bot.get_me().username # Получаем имя пользователя бота
        for amb in ambassadors_data:
            referral_link = f"https://t.me/{bot_username}?start={amb['telegram_id']}"
            text += f"@{amb['username'] or 'N/A'} ({referral_link})\n"
            text += f"- Переходов: {amb['transitions']}\n"
            text += f"- Оплативших: {amb['paid_users']}\n"
            text += f"- Ожидают выплаты: {amb['awaiting_payment']}\n\n"

        bot.send_message(message.chat.id, text)

    # ==============================
    # Управление пользователями
    # ==============================
    
    @bot.message_handler(func=lambda message: message.text == '👤 Управление пользователями')
    def show_users_management(message):
        """Показывает меню управления пользователями"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('🔍 Найти пользователя', '🗑️ Удалить пользователя')
        markup.add('🔙 Назад')
        
        bot.send_message(
            message.chat.id,
            "👤 **Управление пользователями**\n\n"
            "Выберите действие:",
            reply_markup=markup,
            parse_mode='Markdown'
        )

    @bot.message_handler(func=lambda message: message.text == '🔍 Найти пользователя')
    def find_user_step1(message):
        """Запрашивает Telegram ID для поиска пользователя"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(
            message.chat.id,
            "🔍 Введите Telegram ID пользователя для поиска:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, find_user_step2)

    def find_user_step2(message):
        """Обрабатывает поиск пользователя по Telegram ID"""
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Поиск пользователя отменен.")
            return_to_main_menu(message)
            return

        try:
            telegram_id = int(message.text.strip())
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == telegram_id).first()
                if not user:
                    bot.send_message(message.chat.id, f"❌ Пользователь с Telegram ID {telegram_id} не найден.")
                    return

                # Получаем информацию о подписках
                active_subscriptions = db.query(Subscription).filter(
                    Subscription.user_id == telegram_id,
                    Subscription.is_active == True
                ).count()

                total_subscriptions = db.query(Subscription).filter(
                    Subscription.user_id == telegram_id
                ).count()

                # Получаем информацию о платежах
                total_payments = db.query(Payment).filter(
                    Payment.user_id == telegram_id,
                    Payment.status == 'succeeded'
                ).count()

                total_spent = db.query(func.sum(Payment.amount)).filter(
                    Payment.user_id == telegram_id,
                    Payment.status == 'succeeded'
                ).scalar() or 0

                user_info = (
                    f"👤 **Информация о пользователе:**\n\n"
                    f"🆔 Telegram ID: `{user.telegram_id}`\n"
                    f"👤 Имя: {user.first_name or 'Не указано'}\n"
                    f"👤 Фамилия: {user.last_name or 'Не указано'}\n"
                    f"📱 Username: @{user.username or 'Не указан'}\n"
                    f"📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                    f"✅ Активен: {'Да' if user.is_active else 'Нет'}\n"
                    f"👑 Амбассадор: {'Да' if user.is_ambassador else 'Нет'}\n"
                    f"💰 Потрачено: {total_spent:.2f}₽\n\n"
                    f"📊 **Статистика:**\n"
                    f"📦 Всего подписок: {total_subscriptions}\n"
                    f"✅ Активных подписок: {active_subscriptions}\n"
                    f"💳 Успешных платежей: {total_payments}"
                )

                bot.send_message(message.chat.id, user_info, parse_mode='Markdown')

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Ошибка при поиске пользователя: {e}")
            finally:
                db.close()

        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID. Введите число.")
        finally:
            return_to_main_menu(message)

    @bot.message_handler(func=lambda message: message.text == '🗑️ Удалить пользователя')
    def delete_user_step1(message):
        """Запрашивает Telegram ID для удаления пользователя"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        bot.send_message(
            message.chat.id,
            "🗑️ Введите Telegram ID пользователя для удаления:\n\n"
            "⚠️ **ВНИМАНИЕ:** Это действие необратимо! Будут удалены:\n"
            "• Все данные пользователя\n"
            "• Все его подписки\n"
            "• История платежей",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, delete_user_step2)

    def delete_user_step2(message):
        """Обрабатывает удаление пользователя"""
        if message.text == '❌ Отмена':
            bot.send_message(message.chat.id, "Удаление пользователя отменено.")
            return_to_main_menu(message)
            return

        try:
            telegram_id = int(message.text.strip())
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.telegram_id == telegram_id).first()
                if not user:
                    bot.send_message(message.chat.id, f"❌ Пользователь с Telegram ID {telegram_id} не найден.")
                    return

                # Проверяем, не админ ли это
                if telegram_id in Config.ADMIN_USER_IDS:
                    bot.send_message(message.chat.id, "❌ Нельзя удалить администратора!")
                    return

                username = user.username or f"user_{telegram_id}"
                
                # Удаляем связанные данные
                # Сначала удаляем платежи
                db.query(Payment).filter(Payment.user_id == telegram_id).delete()
                
                # Затем подписки
                db.query(Subscription).filter(Subscription.user_id == telegram_id).delete()
                
                # Удаляем из статистики амбассадоров
                db.query(AmbassadorStats).filter(
                    (AmbassadorStats.user_id == telegram_id) | 
                    (AmbassadorStats.referral_id == telegram_id)
                ).delete()
                
                # Наконец удаляем пользователя
                db.delete(user)
                db.commit()

                bot.send_message(
                    message.chat.id,
                    f"✅ Пользователь @{username} (ID: {telegram_id}) успешно удален!\n\n"
                    f"Удалено:\n"
                    f"• Профиль пользователя\n"
                    f"• Все подписки\n"
                    f"• История платежей\n"
                    f"• Статистика амбассадоров"
                )

            except Exception as e:
                bot.send_message(message.chat.id, f"❌ Ошибка при удалении пользователя: {e}")
                db.rollback()
            finally:
                db.close()

        except ValueError:
            bot.send_message(message.chat.id, "❌ Некорректный Telegram ID. Введите число.")
        finally:
            return_to_main_menu(message)

    # ==============================
    # Обработчики управления уведомлениями
    # ==============================
    
    @bot.message_handler(func=lambda message: message.text == '🔔 Управление уведомлениями')
    def show_notifications_menu(message):
        """Показывает меню управления уведомлениями"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📝 Напоминание через 3 часа", callback_data="edit_notification_inactive_3_hours"))
        markup.add(types.InlineKeyboardButton("📝 Напоминание через 3 дня", callback_data="edit_notification_inactive_3_days"))
        markup.add(types.InlineKeyboardButton("📝 Напоминание через 7 дней", callback_data="edit_notification_inactive_7_days"))
        markup.add(types.InlineKeyboardButton("📋 Список всех уведомлений", callback_data="list_all_notifications"))
        markup.add(types.InlineKeyboardButton("🗑️ Удалить все уведомления", callback_data="delete_all_notifications"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin"))
        
        bot.send_message(
            message.chat.id,
            "🔔 **Управление уведомлениями**\n\n"
            "Выберите тип уведомления для редактирования:",
            reply_markup=markup,
            parse_mode='Markdown'
        )

    # Новые простые обработчики для уведомлений
    @bot.callback_query_handler(func=lambda call: call.data.startswith('edit_notification_'))
    def edit_notification_callback(call):
        """Обрабатывает выбор типа уведомления для редактирования"""
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        notification_key = call.data.replace('edit_notification_', '')
        
        # Получаем текущее уведомление, если есть
        current_notification = NotificationService.get_notification_text(notification_key)
        
        if current_notification:
            text = f"✏️ **Редактирование уведомления: {notification_key}**\n\n"
            text += f"📝 Текущий текст:\n{current_notification.text}\n\n"
            text += "📝 **Отправьте новый текст уведомления:**"
        else:
            text = f"➕ **Создание уведомления: {notification_key}**\n\n"
            text += "📝 **Отправьте текст уведомления:**"
        
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None,
            parse_mode='Markdown'
        )
        
        # Создаем объект message для register_next_step_handler
        msg = type('msg', (), {'chat': call.message.chat, 'from_user': call.from_user})()
        bot.register_next_step_handler(msg, lambda msg: save_notification_text(msg, notification_key))
        bot.answer_callback_query(call.id, "✅ Отправьте текст")

    def save_notification_text(message, notification_key):
        """Сохраняет текст уведомления"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return

        try:
            text = message.text.strip()
            if not text:
                bot.send_message(message.chat.id, "❌ Текст не может быть пустым. Попробуйте снова.")
                bot.register_next_step_handler(message, lambda msg: save_notification_text(msg, notification_key))
                return

            # Создаем или обновляем уведомление
            notification = NotificationService.create_or_update_notification_text(
                key=notification_key,
                title=f"Напоминание {notification_key}",
                text=text,
                variant='default',
                trigger_condition=notification_key,
                delay_hours=0,
                priority=1
            )

            if notification:
                bot.send_message(
                    message.chat.id,
                    f"✅ **Уведомление сохранено!**\n\n"
                    f"🔑 Тип: `{notification_key}`\n"
                    f"📝 Текст: {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
                    f"Теперь это уведомление будет отправляться пользователям.",
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(message.chat.id, "❌ Ошибка при сохранении уведомления.")

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == 'list_all_notifications')
    def list_all_notifications_callback(call):
        """Показывает список всех уведомлений"""
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        notifications = NotificationService.get_all_notification_texts()
        
        if not notifications:
            bot.edit_message_text(
                "📋 **Список уведомлений пуст.**\n\nСоздайте уведомления, нажав на кнопки выше.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None,
                parse_mode='Markdown'
            )
            return

        text = "📋 **Список всех уведомлений:**\n\n"
        for i, notification in enumerate(notifications, 1):
            text += f"**{i}. {notification.key}**\n"
            text += f"📝 {notification.text[:150]}{'...' if len(notification.text) > 150 else ''}\n\n"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_notifications"))
        
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "✅ Список уведомлений")

    @bot.callback_query_handler(func=lambda call: call.data == 'delete_all_notifications')
    def delete_all_notifications_callback(call):
        """Удаляет все уведомления"""
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Да, удалить все", callback_data="confirm_delete_all"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete_all"))

        bot.edit_message_text(
            "⚠️ **Внимание!**\n\n"
            "Вы уверены, что хотите удалить ВСЕ уведомления?\n\n"
            "Это действие нельзя отменить!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "⚠️ Подтвердите удаление")

    @bot.callback_query_handler(func=lambda call: call.data == 'confirm_delete_all')
    def confirm_delete_all_callback(call):
        """Подтверждает удаление всех уведомлений"""
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        try:
            # Удаляем все уведомления
            db = SessionLocal()
            try:
                from database.models import NotificationText
                deleted_count = db.query(NotificationText).delete()
                db.commit()
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_notifications"))
                
                bot.edit_message_text(
                    call.message.chat.id,
                    call.message.message_id,
                    f"✅ **Удалено {deleted_count} уведомлений!**\n\n"
                    "Теперь система уведомлений отключена.",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            finally:
                db.close()
                
        except Exception as e:
            bot.edit_message_text(
                call.message.chat.id,
                call.message.message_id,
                f"❌ Ошибка при удалении: {e}",
                reply_markup=None,
                parse_mode='Markdown'
            )
        
        bot.answer_callback_query(call.id, "✅ Удаление завершено")

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete_all')
    def cancel_delete_all_callback(call):
        """Отменяет удаление всех уведомлений"""
        if call.from_user.id not in Config.ADMIN_USER_IDS:
            bot.answer_callback_query(call.id, "❌ Доступ запрещен")
            return

        # Возвращаемся к меню уведомлений
        show_notifications_menu(call.message)
        bot.answer_callback_query(call.id, "❌ Удаление отменено")

    # ==============================
    # Управление материалами марафона
    # ==============================
    
    def show_marathon_materials_menu(message):
        """Показывает меню управления материалами марафона"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            bot.send_message(message.chat.id, "❌ Доступ запрещен")
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('➕ Добавить материал', '📝 Добавить пост')
        markup.add('📋 Список материалов', '📋 Список постов')
        markup.add('🔙 Назад')
        
        bot.send_message(
            message.chat.id,
            "🎯 **Управление материалами марафона**\n\n"
            "Выберите действие:",
            reply_markup=markup,
            parse_mode='Markdown'
        )
    
    admin_marathon_material_data = {}
    
    @bot.message_handler(func=lambda m: m.from_user.id in Config.ADMIN_USER_IDS and m.text == '➕ Добавить материал')
    def add_marathon_material_step1(message):
        """Начало добавления материала"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        
        bot.send_message(
            message.chat.id,
            "📝 **Добавление материала марафона**\n\n"
            "Выберите тип материала:\n"
            "1. training_video - Обучающее видео (отправляется при /start)\n"
            "2. marathon_intro_video - Видео обращение при вступлении в марафон\n"
            "3. category_message - Сообщение для категории при /start\n\n"
            "Введите тип материала (training_video/marathon_intro_video/category_message):",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(message, add_marathon_material_step2)
    
    def add_marathon_material_step2(message):
        """Второй шаг - получение типа материала"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            return
        
        material_type = message.text.strip().lower()
        if material_type not in ['training_video', 'marathon_intro_video', 'category_message']:
            bot.send_message(message.chat.id, "❌ Неверный тип. Используйте: training_video, marathon_intro_video или category_message")
            bot.register_next_step_handler(message, add_marathon_material_step2)
            return
        
        admin_marathon_material_data[message.from_user.id] = {'type': material_type}
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        
        bot.send_message(
            message.chat.id,
            "Введите название материала:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, add_marathon_material_step3)
    
    def add_marathon_material_step3(message):
        """Третий шаг - получение названия"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            return
        
        if message.from_user.id not in admin_marathon_material_data:
            show_marathon_materials_menu(message)
            return
        
        admin_marathon_material_data[message.from_user.id]['title'] = message.text
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена', '⏭️ Пропустить')
        
        bot.send_message(
            message.chat.id,
            "Отправьте видео, фото или документ (или нажмите 'Пропустить' если только текст):",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, add_marathon_material_step4)
    
    def add_marathon_material_step4(message):
        """Четвертый шаг - получение медиа"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            return
        
        if message.from_user.id not in admin_marathon_material_data:
            show_marathon_materials_menu(message)
            return
        
        material_data = admin_marathon_material_data[message.from_user.id]
        file_id = None
        file_type = None
        
        if message.video:
            file_id = message.video.file_id
            file_type = 'video'
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.document:
            file_id = message.document.file_id
            file_type = 'document'
        
        material_data['file_id'] = file_id
        material_data['file_type'] = file_type
        
        if message.text != '⏭️ Пропустить':
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add('❌ Отмена', '⏭️ Пропустить')
            bot.send_message(
                message.chat.id,
                "Введите описание материала (или нажмите 'Пропустить'):",
                reply_markup=markup
            )
            bot.register_next_step_handler(message, add_marathon_material_step5)
        else:
            add_marathon_material_step5(message)
    
    def add_marathon_material_step5(message):
        """Пятый шаг - получение описания и сохранение"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            if message.from_user.id in admin_marathon_material_data:
                del admin_marathon_material_data[message.from_user.id]
            return
        
        if message.from_user.id not in admin_marathon_material_data:
            show_marathon_materials_menu(message)
            return
        
        material_data = admin_marathon_material_data[message.from_user.id]
        description = message.text if message.text != '⏭️ Пропустить' else None
        
        try:
            db = SessionLocal()
            try:
                material = MarathonMaterial(
                    material_type=material_data['type'],
                    title=material_data['title'],
                    description=description,
                    file_id=material_data.get('file_id'),
                    file_type=material_data.get('file_type'),
                    is_active=True
                )
                db.add(material)
                db.commit()
                bot.send_message(message.chat.id, f"✅ Материал '{material_data['title']}' успешно добавлен!")
            finally:
                db.close()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка при добавлении материала: {e}")
            logger.error(f"Ошибка добавления материала марафона: {e}", exc_info=True)
        finally:
            if message.from_user.id in admin_marathon_material_data:
                del admin_marathon_material_data[message.from_user.id]
            show_marathon_materials_menu(message)
    
    @bot.message_handler(func=lambda m: m.from_user.id in Config.ADMIN_USER_IDS and m.text == '📋 Список материалов')
    def list_marathon_materials(message):
        """Показывает список материалов"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return
        
        db = SessionLocal()
        try:
            materials = db.query(MarathonMaterial).all()
            if not materials:
                bot.send_message(message.chat.id, "📋 Список материалов пуст.")
                return
            
            text = "📋 **Список материалов марафона:**\n\n"
            for mat in materials:
                status = "✅ Активен" if mat.is_active else "❌ Неактивен"
                text += f"**{mat.title}** ({mat.material_type})\n"
                text += f"Статус: {status}\n"
                if mat.description:
                    text += f"Описание: {mat.description[:50]}...\n"
                text += f"ID: {mat.id}\n\n"
            
            bot.send_message(message.chat.id, text, parse_mode='Markdown')
        finally:
            db.close()
    
    @bot.message_handler(func=lambda m: m.from_user.id in Config.ADMIN_USER_IDS and m.text == '📝 Добавить пост')
    def add_marathon_post_step1(message):
        """Начало добавления поста"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        
        bot.send_message(
            message.chat.id,
            "📝 **Добавление поста марафона**\n\n"
            "Выберите тип поста:\n"
            "1. warmup - Догревочный пост\n"
            "2. hard - Жесткий пост\n\n"
            "Введите тип поста (warmup/hard):",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(message, add_marathon_post_step2)
    
    admin_marathon_post_data = {}
    
    def add_marathon_post_step2(message):
        """Второй шаг - получение типа поста"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            return
        
        post_type = message.text.strip().lower()
        if post_type not in ['warmup', 'hard']:
            bot.send_message(message.chat.id, "❌ Неверный тип. Используйте: warmup или hard")
            bot.register_next_step_handler(message, add_marathon_post_step2)
            return
        
        admin_marathon_post_data[message.from_user.id] = {'type': post_type}
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        
        bot.send_message(
            message.chat.id,
            "Введите номер дня (1-7):",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, add_marathon_post_step3)
    
    def add_marathon_post_step3(message):
        """Третий шаг - получение номера дня"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            return
        
        try:
            day_number = int(message.text.strip())
            if day_number < 1 or day_number > 7:
                raise ValueError
        except ValueError:
            bot.send_message(message.chat.id, "❌ Неверный номер дня. Введите число от 1 до 7")
            bot.register_next_step_handler(message, add_marathon_post_step3)
            return
        
        if message.from_user.id not in admin_marathon_post_data:
            show_marathon_materials_menu(message)
            return
        
        admin_marathon_post_data[message.from_user.id]['day_number'] = day_number
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add('❌ Отмена')
        
        bot.send_message(
            message.chat.id,
            "Введите текст поста:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, add_marathon_post_step4)
    
    def add_marathon_post_step4(message):
        """Четвертый шаг - получение текста и сохранение"""
        if message.text == '❌ Отмена':
            show_marathon_materials_menu(message)
            if message.from_user.id in admin_marathon_post_data:
                del admin_marathon_post_data[message.from_user.id]
            return
        
        if message.from_user.id not in admin_marathon_post_data:
            show_marathon_materials_menu(message)
            return
        
        post_data = admin_marathon_post_data[message.from_user.id]
        text_content = message.text
        
        # Проверяем, есть ли медиа
        file_id = None
        file_type = None
        
        if message.video:
            file_id = message.video.file_id
            file_type = 'video'
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.document:
            file_id = message.document.file_id
            file_type = 'document'
        
        try:
            db = SessionLocal()
            try:
                post = MarathonPost(
                    post_type=post_data['type'],
                    day_number=post_data['day_number'],
                    text_content=text_content,
                    file_id=file_id,
                    file_type=file_type,
                    is_active=True
                )
                db.add(post)
                db.commit()
                bot.send_message(message.chat.id, f"✅ Пост для дня {post_data['day_number']} успешно добавлен!")
            finally:
                db.close()
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка при добавлении поста: {e}")
            logger.error(f"Ошибка добавления поста марафона: {e}", exc_info=True)
        finally:
            if message.from_user.id in admin_marathon_post_data:
                del admin_marathon_post_data[message.from_user.id]
            show_marathon_materials_menu(message)
    
    @bot.message_handler(func=lambda m: m.from_user.id in Config.ADMIN_USER_IDS and m.text == '📋 Список постов')
    def list_marathon_posts(message):
        """Показывает список постов"""
        if message.from_user.id not in Config.ADMIN_USER_IDS:
            return
        
        db = SessionLocal()
        try:
            posts = db.query(MarathonPost).all()
            if not posts:
                bot.send_message(message.chat.id, "📋 Список постов пуст.")
                return
            
            text = "📋 **Список постов марафона:**\n\n"
            for post in posts:
                status = "✅ Активен" if post.is_active else "❌ Неактивен"
                text += f"**День {post.day_number}** ({post.post_type})\n"
                text += f"Статус: {status}\n"
                text += f"Текст: {post.text_content[:50]}...\n"
                text += f"ID: {post.id}\n\n"
            
            bot.send_message(message.chat.id, text, parse_mode='Markdown')
        finally:
            db.close()