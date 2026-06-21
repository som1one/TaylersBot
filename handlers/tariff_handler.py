import datetime
import logging
from telebot import types
from database.models import Tariff, Subscription
from database.connection import SessionLocal
from config import Config
from services.payment_service_alt import PaymentService
from services.user_service import UserService
from services.link_protection_service import LinkProtectionService
from handlers.error_handler import strip_premium_emoji

logger = logging.getLogger(__name__)

user_tariff_data = {}

def register_tariff_handlers(bot, payment_service=None):
    """Регистрирует обработчики для работы с тарифами"""

    if payment_service is None:
        payment_service = PaymentService()
    
    def update_user_activity(user_telegram_id):
        """Обновляет активность пользователя"""
        try:
            from services.user_activity_service import UserActivityService
            temp_activity_service = UserActivityService(bot)
            temp_activity_service.update_user_activity(user_telegram_id)
        except Exception as e:
            logger.error(f"Ошибка обновления активности пользователя {user_telegram_id}: {e}")

    @bot.message_handler(commands=['tariffs'])
    def show_tariffs_command(message):
        """Показывает доступные тарифы"""
        db = SessionLocal()
        try:
            tariffs = db.query(Tariff).filter(Tariff.is_active == True).all()
            if not tariffs:
                bot.send_message(message.chat.id, "😔 К сожалению, сейчас нет доступных тарифов.")
                return

            text = "💰 Доступные тарифы:\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)

            for tariff in tariffs:
                duration_text = f"{tariff.duration_days} дней" if tariff.duration_days else "Навсегда"
                text += f"📦 **{tariff.name}**\n"
                text += f"   💰 Цена: **{tariff.price}₽**\n"
                text += f"   ⏱️ Длительность: **{duration_text}**\n"
                if tariff.description:
                    text += f"   📝 {strip_premium_emoji(tariff.description)}\n"
                text += "\n"

                markup.add(types.InlineKeyboardButton(
                    f"💳 Купить {tariff.name} - {tariff.price}₽",
                    callback_data=f"buy_tariff_{tariff.id}"
                ))

            bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='Markdown')

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка при загрузке тарифов: {e}")
        finally:
            db.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_tariff_'))
    def handle_buy_tariff(call):
        """Обрабатывает покупку тарифа"""
        
        # Обновляем активность пользователя
        update_user_activity(call.from_user.id)
        db = SessionLocal()
        try:
            tariff_id = int(call.data.split('_')[2])

            tariff = db.query(Tariff).filter(Tariff.id == tariff_id, Tariff.is_active == True).first()
            if not tariff:
                bot.answer_callback_query(call.id, "❌ Тариф не найден или неактивен")
                return

            user = UserService.get_user_by_telegram_id(call.from_user.id)
            if not user:
                bot.answer_callback_query(call.id, "❌ Пользователь не найден")
                return

            active_subscription = db.query(Subscription).filter(
                Subscription.user_id == user.telegram_id,
                Subscription.is_active == True
            ).first()

            if active_subscription:
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("🔄 Заменить подписку", callback_data=f"confirm_replace_{tariff_id}"),
                    types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_purchase")
                )

                text = f"⚠️ У вас уже есть активная подписка!\n\n"
                text += f"📅 Действует до: {active_subscription.end_date.strftime('%d.%m.%Y')}\n\n"
                text += f"Хотите заменить её на тариф **{tariff.name}**?"

                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                return

            payment_result = payment_service.create_payment(
                user_id=user.telegram_id,
                tariff_id=tariff.id,
                amount=tariff.price,
                description=f"Подписка на тариф '{tariff.name}'"
            )

            if payment_result:
                # Планируем уведомление о неоконченной оплате
                try:
                    from services.notification_sender_service import NotificationSenderService
                    temp_notification_service = NotificationSenderService(bot)
                    temp_notification_service.schedule_user_activity_notification(user.telegram_id, 'payment_not_completed')
                    logger.info(f"[handle_buy_tariff] Запланировано уведомление о неоконченной оплате для пользователя {user.telegram_id}")
                except Exception as e:
                    logger.error(f"[handle_buy_tariff] Ошибка планирования уведомления для {user.telegram_id}: {e}")
                text = f"💳 **Оплата тарифа '{tariff.name}'**\n\n"
                text += f"💰 Сумма: **{tariff.price}₽**\n"
                text += f"⏱️ Длительность: **{tariff.duration_days if tariff.duration_days else 'Навсегда'}**\n"
                text += f"📝 Описание: {strip_premium_emoji(tariff.description) or 'Нет описания'}\n\n"
                text += f"🆔 ID платежа: `{payment_result['payment_id']}`\n\n"

                confirmation_url = payment_result.get('confirmation_url')
                if confirmation_url:
                    text += f"Для оплаты нажмите кнопку ниже:\n\n🔗 {confirmation_url}"

                markup = types.InlineKeyboardMarkup(row_width=2)
                buttons_row = []
                if confirmation_url:
                    buttons_row.append(types.InlineKeyboardButton("💳 Оплатить", url=confirmation_url))
                buttons_row.append(types.InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_status_{payment_result['payment_id']}"))
                markup.add(*buttons_row)
                markup.add(types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_payment"))

                bot.edit_message_text(
                    text,
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                bot.answer_callback_query(call.id, "✅ Платеж создан! Нажмите 'Оплатить'.")
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка создания платежа")

        except Exception as e:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
        finally:
            db.close()
