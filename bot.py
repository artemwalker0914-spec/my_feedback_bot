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
    await update.message.reply_text(
        "👋 Привет! Напиши мне сообщение — оно будет отправлено учителям."
    )

async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    if user.id not in student_to_topic:
        try:
            # Название темы без ссылки на пользователя
            topic_name = f"Ученик {user.full_name}"
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=topic_name
            )
            thread_id = topic.message_thread_id
            
            student_to_topic[user.id] = thread_id
            topic_to_student[thread_id] = user.id
            
            await update.message.reply_text("✅ Сообщение отправлено учителям.")
        except Exception as e:
            logging.error(f"Ошибка создания темы: {e}")
            await update.message.reply_text("❌ Ошибка создания темы.")
            return

    thread_id = student_to_topic[user.id]
    try:
        await message.forward(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=thread_id
        )
    except Exception as e:
        logging.error(f"Ошибка пересылки ученика: {e}")

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает ответ учителя ученику"""
    message = update.message
    if not message or not message.message_thread_id:
        return

    thread_id = message.message_thread_id
    student_id = topic_to_student.get(thread_id)

    if student_id:
        try:
            # Пересылаем без лишней информации
            await message.forward(chat_id=student_id)
            logging.info(f"Ответ учителя → ученику {student_id}")
        except Exception as e:
            logging.error(f"Не удалось отправить ответ ученику {student_id}: {e}")

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

    print("🤖 Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
