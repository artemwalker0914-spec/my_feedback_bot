import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ================== НАСТРОЙКИ ==================
TOKEN = "8861477655:AAFOTTHikYcHWwP19p790B03363Oz6O72H8"
GROUP_CHAT_ID = -1003721858380
# ===============================================

student_to_topic = {}
topic_to_student = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Пиши сообщение — оно будет отправлено учителям без указания твоего аккаунта.")

async def copy_message_to_chat(update: Update, chat_id: int, message_thread_id: int = None):
    """Копирует сообщение без 'Forwarded from'"""
    message = update.message
    try:
        if message.text:
            await update.message.reply_text(
                text=message.text,
                chat_id=chat_id,
                message_thread_id=message_thread_id
            )
        elif message.photo:
            await update.message.reply_photo(
                photo=message.photo[-1].file_id,
                caption=message.caption,
                chat_id=chat_id,
                message_thread_id=message_thread_id
            )
        elif message.voice:
            await update.message.reply_voice(
                voice=message.voice.file_id,
                caption=message.caption,
                chat_id=chat_id,
                message_thread_id=message_thread_id
            )
        elif message.video:
            await update.message.reply_video(
                video=message.video.file_id,
                caption=message.caption,
                chat_id=chat_id,
                message_thread_id=message_thread_id
            )
        elif message.document:
            await update.message.reply_document(
                document=message.document.file_id,
                caption=message.caption,
                chat_id=chat_id,
                message_thread_id=message_thread_id
            )
        else:
            # Для остальных типов пока используем forward
            await message.forward(chat_id=chat_id, message_thread_id=message_thread_id)
    except Exception as e:
        logging.error(f"Ошибка копирования сообщения: {e}")
        await message.forward(chat_id=chat_id, message_thread_id=message_thread_id)

async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if user.id not in student_to_topic:
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"Ученик {user.full_name}"
            )
            thread_id = topic.message_thread_id
            student_to_topic[user.id] = thread_id
            topic_to_student[thread_id] = user.id
            await update.message.reply_text("✅ Сообщение отправлено учителям.")
        except Exception as e:
            logging.error(f"Ошибка создания темы: {e}")
            return

    thread_id = student_to_topic[user.id]
    await copy_message_to_chat(update, GROUP_CHAT_ID, thread_id)

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        return

    thread_id = message.message_thread_id
    student_id = topic_to_student.get(thread_id)

    if student_id:
        try:
            # Копируем ответ учителя ученику тоже без "Forwarded from"
            await copy_message_to_chat(update, student_id)
        except Exception as e:
            logging.error(f"Ошибка отправки ученику: {e}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_student_message
    ))
    
    application.add_handler(MessageHandler(
        filters.ChatType.SUPERGROUP,
        handle_teacher_reply
    ))

    print("🤖 Бот запущен (без Forwarded from)")
    application.run_polling()

if __name__ == '__main__':
    main()
