import datetime
import logging
from telebot import types
from database.models import Tariff
from database.connection import SessionLocal
from services.payment_service_alt import PaymentService
from handlers.error_handler import strip_premium_emoji

logger = logging.getLogger(__name__)


def register_tariff_handlers(bot, payment_service=None):
    """Регистрирует команду /tariffs для показа доступных тарифов.

    Покупка и оплата (карта/крипта) обрабатываются в user_handlers.py через
    callback_data 'buy_tariff_*', 'pay_tariff_*' и 'pay_crypto_*'.
    """

    if payment_service is None:
        payment_service = PaymentService()

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
