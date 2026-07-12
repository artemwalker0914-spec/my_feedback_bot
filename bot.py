import logging
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO)

# ================== НАСТРОЙКИ ==================
TOKEN = "8861477655:AAFOTTHikYcHWwP19p790B03363Oz6O72H8"
GROUP_CHAT_ID = -1003721858380      # ←←← ИЗМЕНИТЬ
# ===============================================

# Хранилище: student_id → topic_id
student_to_topic = {}
topic_to_student = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я буду пересылать твои сообщения учителям.\n"
        "Просто пиши сюда — всё дойдёт."
    )

async def handle_student_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message
    
    if user.id not in student_to_topic:
        # Создаём новую тему
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_CHAT_ID,
            name=f"{user.full_name} ({user.id})"
        )
        student_to_topic[user.id] = topic.message_thread_id
        topic_to_student[topic.message_thread_id] = user.id
        
        await message.reply_text("✅ Тема создана. Сообщение отправлено учителям.")

    thread_id = student_to_topic[user.id]
    
    # Пересылаем сообщение в тему
    await message.forward(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=thread_id
    )

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответы учителя в темах"""
    message = update.message
    if not message or not message.message_thread_id:
        return
    
    thread_id = message.message_thread_id
    student_id = topic_to_student.get(thread_id)
    
    if not student_id:
        return  # Неизвестная тема
    
    # Пересылаем ответ ученику
    try:
        await message.forward(chat_id=student_id)
    except Exception as e:
        logging.error(f"Не удалось переслать учителя ученику {student_id}: {e}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    
    # Сообщения от учеников в личку
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.CHAT_TYPE.PRIVATE,
        handle_student_message
    ))
    
    # Ответы учителей в группе (в темах)
    app.add_handler(MessageHandler(
        filters.CHAT_TYPE.SUPERGROUP,
        handle_teacher_reply
    ))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
