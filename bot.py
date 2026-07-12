import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Включаем подробное логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)

# ================== НАСТРОЙКИ ==================
TOKEN = "8861477655:AAFOTTHikYcHWwP19p790B03363Oz6O72H8"
GROUP_CHAT_ID = -1003721858380
# ===============================================

student_to_topic = {}
topic_to_student = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Команда /start от пользователя {update.effective_user.id}")
    await update.message.reply_text("👋 Бот работает. Напиши любое сообщение.")

async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text if update.message.text else "Не текст"
    
    logging.info(f"📨 Сообщение от ученика {user.id} ({user.full_name}): {text}")
    
    if user.id not in student_to_topic:
        logging.info(f"Создаём новую тему для ученика {user.id}")
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"Ученик {user.full_name}"
            )
            thread_id = topic.message_thread_id
            student_to_topic[user.id] = thread_id
            topic_to_student[thread_id] = user.id
            logging.info(f"Тема создана: {thread_id}")
            await update.message.reply_text("✅ Тема создана. Сообщение отправлено.")
        except Exception as e:
            logging.error(f"Ошибка создания темы: {e}")
            return

    thread_id = student_to_topic[user.id]
    try:
        await update.message.forward(chat_id=GROUP_CHAT_ID, message_thread_id=thread_id)
        logging.info(f"Сообщение успешно переслано в тему {thread_id}")
    except Exception as e:
        logging.error(f"Ошибка пересылки: {e}")

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.message_thread_id:
        logging.debug("Получено сообщение без thread_id")
        return
    
    thread_id = update.message.message_thread_id
    student_id = topic_to_student.get(thread_id)
    
    logging.info(f"Ответ в теме {thread_id}. Ученик: {student_id}")
    
    if student_id:
        try:
            await update.message.forward(chat_id=student_id)
            logging.info(f"✅ Ответ успешно переслан ученику {student_id}")
        except Exception as e:
            logging.error(f"❌ Ошибка пересылки учителя → ученику: {e}")

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

    print("🤖 Бот запущен с DEBUG логами...")
    application.run_polling()

if __name__ == '__main__':
    main()
