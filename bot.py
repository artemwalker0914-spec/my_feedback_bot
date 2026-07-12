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
    await update.message.reply_text("👋 Пиши сообщение. Учителя увидят текст без твоего аккаунта.")

async def safe_copy_message(context, from_chat_id: int, message_id: int, to_chat_id: int, message_thread_id: int = None):
    """Копирует сообщение без 'Forwarded from'"""
    try:
        await context.bot.copy_message(
            chat_id=to_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            message_thread_id=message_thread_id
        )
        return True
    except Exception as e:
        logging.error(f"Ошибка copy_message: {e}")
        # Fallback
        try:
            await context.bot.forward_message(
                chat_id=to_chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                message_thread_id=message_thread_id
            )
        except:
            pass
        return False

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
            await update.message.reply_text("✅ Отправлено учителям.")
        except Exception as e:
            logging.error(f"Ошибка темы: {e}")
            return

    thread_id = student_to_topic[user.id]
    await safe_copy_message(
        context=context,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        to_chat_id=GROUP_CHAT_ID,
        message_thread_id=thread_id
    )

async def handle_teacher_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        return

    thread_id = message.message_thread_id
    student_id = topic_to_student.get(thread_id)

    if student_id:
        await safe_copy_message(
            context=context,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            to_chat_id=student_id
        )

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

    print("🤖 Бот запущен (copy_message)")
    application.run_polling()

if __name__ == '__main__':
    main()
