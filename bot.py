import logging
import json
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКИ ---
TOKEN = "8861477655:AAFOTTHikYcHWwP19p790B03363Oz6O72H8"
GROUP_ID = -1003721858380
# -----------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # DEBUG для максимальной отладки
)
logger = logging.getLogger(__name__)

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
    else:
        logger.info("Файл маппинга не найден.")

def save_mapping():
    try:
        with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_topic_map, f, ensure_ascii=False, indent=2)
        logger.info("Маппинг сохранён.")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Привет, {update.effective_user.first_name}! 👋\nСообщения будут пересылаться учителям.")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    # ... (ваш код создания темы и отправки в группу — оставьте как есть)
    # (я не менял эту часть)

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.id != GROUP_ID:
        return

    logger.debug(f"Получено сообщение в группе. Thread ID: {message.message_thread_id}, Reply to: {message.reply_to_message}")

    topic_id = message.message_thread_id
    user_id = None
    for uid, tid in user_topic_map.items():
        if tid == topic_id:
            user_id = uid
            break

    if user_id is None:
        logger.warning(f"Не найден пользователь для темы {topic_id}")
        return

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"👩‍🏫 Ответ от учителя:\n\n{message.text}"
        )
        await message.reply_text("✅ Ответ отправлен.")
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")

async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Максимально подробный лог ВСЕХ обновлений"""
    if update.message:
        msg = update.message
        logger.info(
            f"UPDATE | Тип чата: {msg.chat.type} | Chat ID: {msg.chat.id} | "
            f"Thread: {getattr(msg, 'message_thread_id', None)} | "
            f"От: {msg.from_user.full_name} | Текст: {msg.text} | "
            f"Reply to: {getattr(msg.reply_to_message, 'message_id', None) if msg.reply_to_message else None}"
        )

def main():
    load_mapping()
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    # Важно: конкретные обработчики — первыми
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_user_message))
    
    application.add_handler(MessageHandler(
        filters.Chat(chat_id=GROUP_ID) & filters.TEXT,  # Шире, чем только REPLY
        handle_teacher_reply
    ))

    # Debug — последним, чтобы не перехватывал
    application.add_handler(MessageHandler(filters.ALL, log_all_updates))

    logger.info("Бот запущен...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True  # Полезно при перезапуске
    )

if __name__ == '__main__':
    main()
