import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКИ (Замените на свои!) ---
TOKEN = "8639656890:AAHOfXP_GA7Ve7wQD1WNjQY3pV_U-4FhMD0"  # Вставьте сюда ваш токен
GROUP_ID = -1003721858380  # Вставьте ID вашей группы (это отрицательное число!)
# -------------------------------------

# Включаем логирование, чтобы видеть, что бот работает
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище для связи "ID ученика" и "ID темы в группе"
user_topic_map = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие при команде /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот-помощник школы «Юниверсум».\n"
        "Теперь все твои сообщения будут видеть наши учителя.\n"
        "Они обязательно тебе ответят! 😊"
    )

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений от учеников (в личке)"""
    user = update.effective_user
    message = update.message

    # Проверяем, что это личное сообщение
    if message.chat.type != "private":
        return

    # Проверяем, есть ли уже тема для этого ученика
    topic_id = user_topic_map.get(user.id)

    if topic_id is None:
        # Если темы нет, создаём новую тему в группе
        try:
            # Создаём тему с именем ученика
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_ID,
                name=f"Ученик: {user.full_name}",
                icon_color=0x6FB9F0
            )
            topic_id = topic.message_thread_id
            user_topic_map[user.id] = topic_id
            logger.info(f"Создана новая тема для {user.full_name} (ID: {topic_id})")
        except Exception as e:
            logger.error(f"Не удалось создать тему: {e}")
            await message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
            return

    # Отправляем сообщение от ученика в его тему в группе
    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=f"📩 Сообщение от {user.full_name} (@{user.username or 'без ника'}):\n\n{message.text}"
        )
        # Отправляем ученику подтверждение
        await message.reply_text("✅ Ваше сообщение отправлено учителям. Мы скоро ответим!")
    except Exception as e:
        logger.error(f"Ошибка при отправке в группу: {e}")
        await message.reply_text("❌ Не удалось отправить сообщение. Попробуйте позже.")

async def log_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирует все сообщения из группы (отладочный)"""
    if update.message and update.message.chat.type in ["group", "supergroup"]:
        logger.info(f"Получено сообщение из группы: {update.message.text} (от {update.message.from_user.full_name})")

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ответов учителей в группе (в теме ученика)"""
    message = update.message

    # Проверяем, что это сообщение из группы и является ответом на другое сообщение
    if message.chat.type not in ["group", "supergroup"] or message.reply_to_message is None:
        return

    logger.info(f"handle_teacher_reply вызвана, сообщение: {message.text}")

    # Пытаемся найти ID ученика по ID темы
    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topic_map.items():
        if tid == topic_id:
            user_id = uid
            break

    if user_id is None:
        logger.warning(f"Не найден ученик для темы {topic_id}")
        await message.reply_text("⚠️ Не удалось определить ученика для этого сообщения.")
        return

    # Отправляем ответ учителя ученику
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"👩‍🏫 Ответ от учителя:\n\n{message.text}"
        )
        # Добавляем пометку в группе, что ответ отправлен
        await message.reply_text("✅ Ответ отправлен ученику.")
        logger.info(f"Ответ отправлен ученику {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа ученику: {e}")
        await message.reply_text("❌ Не удалось отправить ответ ученику.")

def main():
    """Запуск бота"""
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

    # Отладочный обработчик для всех сообщений из группы
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=GROUP_ID) & filters.TEXT,
        log_group_messages
    ))

    # Обработчик для ответов в группе (фильтр: сообщение из группы, ответ на другое сообщение)
    application.add_handler(MessageHandler(
        filters.REPLY & filters.Chat(chat_id=GROUP_ID),
        handle_teacher_reply
    ))

    # Запускаем бота (используем polling)
    logger.info("Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
