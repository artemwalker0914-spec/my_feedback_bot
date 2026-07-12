import logging
import json
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКИ (Замените на свои!) ---
TOKEN = "8950928509:AAGfkJMlNBopWzNQzJ7Gn7SIkcbwMZ_Nvd0"                # Вставьте сюда ваш токен от @BotFather
GROUP_ID = -1003721858380          # Вставьте ID вашей группы (отрицательное число!)
# -------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Файл для хранения маппинга
MAPPING_FILE = "user_topic_map.json"
user_topic_map = {}

def load_mapping():
    global user_topic_map
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_topic_map = {int(k): v for k, v in data.items()}
            logger.info(f"Загружено {len(user_topic_map)} соответствий.")
        except Exception as e:
            logger.error(f"Ошибка загрузки маппинга: {e}")
            user_topic_map = {}
    else:
        logger.info("Файл маппинга не найден, начинаем с пустого словаря.")

def save_mapping():
    try:
        with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_topic_map, f, ensure_ascii=False, indent=2)
        logger.info("Маппинг сохранён.")
    except Exception as e:
        logger.error(f"Ошибка сохранения маппинга: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот-помощник школы «Юниверсум».\n"
        "Теперь все твои сообщения будут видны нашим учителям.\n"
        "Они обязательно тебе ответят! 😊"
    )

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if message.chat.type != "private":
        return

    topic_id = user_topic_map.get(user.id)

    if topic_id is None:
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_ID,
                name=f"Ученик: {user.full_name}",
                icon_color=0x6FB9F0
            )
            topic_id = topic.message_thread_id
            user_topic_map[user.id] = topic_id
            save_mapping()
            logger.info(f"Создана новая тема для {user.full_name} (ID: {topic_id})")
        except Exception as e:
            logger.error(f"Не удалось создать тему: {e}")
            await message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
            return

    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=topic_id,
            text=f"📩 Сообщение от {user.full_name} (@{user.username or 'без ника'}):\n\n{message.text}"
        )
        await message.reply_text("✅ Ваше сообщение отправлено учителям. Мы скоро ответим!")
    except Exception as e:
        logger.error(f"Ошибка при отправке в группу: {e}")
        await message.reply_text("❌ Не удалось отправить сообщение. Попробуйте позже.")

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if message.chat.type not in ["group", "supergroup"]:
        return
    if message.reply_to_message is None:
        return

    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topic_map.items():
        if tid == topic_id:
            user_id = uid
            break

    if user_id is None:
        await message.reply_text("⚠️ Не удалось определить ученика для этого сообщения.")
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"👩‍🏫 Ответ от учителя:\n\n{message.text}"
        )
        await message.reply_text("✅ Ответ отправлен ученику.")
    except Exception as e:
        logger.error(f"Ошибка при отправке ответа ученику: {e}")
        await message.reply_text("❌ Не удалось отправить ответ ученику.")

# ========== ОТЛАДОЧНЫЙ ОБРАБОТЧИК (без фильтра по chat_id) ==========
async def log_all_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Логирует все текстовые сообщения из любых чатов (личные и группы)"""
    if update.message and update.message.text:
        chat_type = update.message.chat.type
        chat_id = update.message.chat.id
        user_name = update.message.from_user.full_name
        text = update.message.text
        logger.info(f"СООБЩЕНИЕ: тип={chat_type}, chat_id={chat_id}, от={user_name}, текст={text}")
# ======================================================================

def main():
    load_mapping()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    application.add_handler(MessageHandler(
        filters.REPLY & filters.Chat(chat_id=GROUP_ID),
        handle_teacher_reply
    ))

    # ===== ОТЛАДОЧНЫЙ ОБРАБОТЧИК (без фильтра) =====
    application.add_handler(MessageHandler(
        filters.TEXT,  # <--- здесь нет фильтра по чату!
        log_all_group_messages
    ))
    # ================================================

    logger.info("Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
