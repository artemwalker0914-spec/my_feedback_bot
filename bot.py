import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ================== НАСТРОЙКИ ==================
TOKEN = "8861477655:AAFOTTHikYcHWwP19p790B03363Oz6O72H8"
GROUP_CHAT_ID = -1003721858380   # ← Ваш ID группы
# ===============================================

# Хранилища (соответствие ученик ↔ тема)
student_to_topic = {}
topic_to_student = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Напиши мне любое сообщение — "
        "оно будет отправлено учителям в отдельной теме."
    )

async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    # Создаём новую тему для ученика, если её ещё нет
    if user.id not in student_to_topic:
        try:
            topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"👤 {user.full_name}"
            )
            thread_id = topic.message_thread_id
            
            student_to_topic[user.id] = thread_id
            topic_to_student[thread_id] = user.id
            
            await update.message.reply_text("✅ Тема создана. Сообщение отправлено учителям.")
        except Exception as e:
            logging.error(f"Ошибка создания темы: {e}")
            await update.message.reply_text("❌ Не удалось создать тему. Проверьте права бота.")
            return

    # Пересылаем сообщение в тему
    thread_id = student_to_topic[user.id]
    try:
        await message.forward(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=thread_id
        )
    except Exception as e:
        logging.error(f"Ошибка пересылки сообщения: {e}")

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает ответ учителя обратно ученику"""
    message = update.message
    if not message or not message.message_thread_id:
        return

    thread_id = message.message_thread_id
    student_id = topic_to_student.get(thread_id)

    if student_id:
        try:
            await message.forward(chat_id=student_id)
            logging.info(f"Ответ учителя переслан ученику {student_id}")
        except Exception as e:
            logging.error(f"Ошибка отправки ответа ученику {student_id}: {e}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    
    # Сообщения от учеников в личку
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.CHAT_TYPE.PRIVATE,
        handle_student_message
    ))
    
    # Ответы учителей в супергруппе
    application.add_handler(MessageHandler(
        filters.CHAT_TYPE.SUPERGROUP,
        handle_teacher_reply
    ))

    print("🤖 Бот запущен и готов к работе...")
    application.run_polling()

if __name__ == '__main__':
    main()
