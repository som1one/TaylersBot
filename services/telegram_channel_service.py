import time

import telebot
from telebot import types
import logging
from config import Config

logger = logging.getLogger(__name__)

class TelegramChannelService:
    def __init__(self, bot: telebot.TeleBot):
        self.bot = bot
        self.channel_id = Config.TELEGRAM_CHANNEL_ID

    def add_user_to_channel(self, user_id: int):
        try:
            logger.info(f"[add_user_to_channel] Создание одноразовой ссылки для пользователя {user_id}")

            # Проверяем права бота в канале
            try:
                bot_member = self.bot.get_chat_member(self.channel_id, self.bot.get_me().id)
                if bot_member.status not in ['administrator', 'creator']:
                    logger.error(f"Бот не является администратором канала {self.channel_id}")
                    return False
            except Exception as e:
                logger.error(f"Ошибка проверки прав бота в канале {self.channel_id}: {e}")
                return False

            # Создаем уникальную ссылку на канал, действительную 10 минут (600 секунд)
            join_link = self.bot.create_chat_invite_link(
                chat_id=self.channel_id,
                member_limit=1,  # Только один человек может вступить
                expire_date=int(time.time()) + 600  # Время жизни 10 минут
            ).invite_link

            # Кнопка с ссылкой
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Перейти в канал", url=join_link))

            # Отправляем пользователю
            self.bot.send_message(
                user_id,
                "🎉 Поздравляем с покупкой подписки!\n\n"
                "Нажмите кнопку ниже, чтобы получить доступ к каналу (ссылка действует 10 минут):",
                reply_markup=markup
            )

            logger.info(
                f"[add_user_to_channel] Одноразовая ссылка создана и отправлена пользователю {user_id}: {join_link}")
            return True

        except telebot.apihelper.ApiTelegramException as e:
            err_text = str(e).lower()
            if "user is a member" in err_text:
                logger.info(f"Пользователь {user_id} уже состоит в канале {self.channel_id}.")
                return True
            elif "user not found" in err_text:
                logger.warning(f"Пользователь {user_id} не найден — не удалось добавить в канал {self.channel_id}.")
            elif "bot is not a member" in err_text or "chat_write_forbidden" in err_text:
                logger.error(
                    f"Бот не является админом канала {self.channel_id} или не может писать пользователю {user_id}.")
            elif "peer_id_invalid" in err_text:
                logger.error(f"Некорректный user_id {user_id} или channel_id {self.channel_id}.")
            else:
                logger.error(f"Ошибка API при добавлении пользователя {user_id} в канал {self.channel_id}: {e}")
            return False

        except Exception as e:
            logger.error(f"[add_user_to_channel] Непредвиденная ошибка: {e}", exc_info=True)
            return False

    def remove_user_from_channel(self, user_id: int):
        try:
            # Проверим, является ли пользователь членом канала
            member = self.bot.get_chat_member(self.channel_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                logger.info(f"Пользователь {user_id} уже не является членом канала {self.channel_id}")
                return True
            
            # Удаляем пользователя из канала (кикаем)
            self.bot.kick_chat_member(self.channel_id, user_id)
            logger.info(f"Пользователь {user_id} удален из канала {self.channel_id}")
            return True
        except telebot.apihelper.ApiTelegramException as e:
            if "user not found" in str(e):
                logger.warning(f"Пользователь {user_id} не найден. Не удалось удалить из канала {self.channel_id}.")
                return False
            elif "USER_NOT_PARTICIPANT" in str(e):
                logger.info(f"Пользователь {user_id} уже не является участником канала {self.channel_id}.")
                return True
            elif "Not enough rights to restrict/unrestrict chat member" in str(e):
                logger.error(f"У бота недостаточно прав для удаления пользователя {user_id} из канала {self.channel_id}. Ошибка: {e}")
                return False
            else:
                logger.error(f"Ошибка при удалении пользователя {user_id} из канала {self.channel_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при удалении пользователя {user_id} из канала {self.channel_id}: {e}")
            return False
