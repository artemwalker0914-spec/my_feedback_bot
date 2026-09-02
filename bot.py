import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from storage import (
    Storage,
    ROLE_STUDENT,
    ROLE_PARENT,
    ROLE_TEACHER,
    ROLE_LABELS_RU,
    ROLE_NAMES_RU,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== НАСТРОЙКИ ==================
TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])

ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x
}

DB_PATH = os.environ.get("DB_PATH", "univ_bot.db")
# ===============================================

storage = Storage(DB_PATH)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def role_label(role: str) -> str:
    return ROLE_LABELS_RU.get(role, "Участника")


# -------------------- /start --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    existing = storage.get_user(user.id)

    if existing and existing["room_id"]:
        room = storage.get_room(existing["room_id"])
        if room is None:
            storage.clear_user_room(user.id)
            existing = None
        else:
            await message.reply_text(
                f"👋 С возвращением! Вы уже в комнате «{room['name']}» "
                f"как {ROLE_NAMES_RU.get(existing['role'], existing['role'])}.\n"
                "Просто напишите сообщение — оно уйдёт учителю."
            )
            return

    invite = storage.pop_pending_invite_for(user.id, user.username)
    if invite:
        room = storage.get_room(invite["room_id"])
        if room is None:
            storage.clear_pending_invite(invite["invite_id"])
            invite = None
        else:
            storage.upsert_user(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=invite["role"],
                room_id=invite["room_id"],
            )
            await message.reply_text(
                f"✅ Вы добавлены в комнату «{room['name']}» как "
                f"{ROLE_NAMES_RU.get(invite['role'], invite['role'])}.\n"
                "Теперь все сообщения из этой комнаты будут приходить сюда, "
                "и ваши сообщения будут туда пересылаться."
            )
            await notify_room(
                context,
                room["room_id"],
                exclude_user_id=user.id,
                text=f"ℹ️ К комнате «{room['name']}» присоединился ещё один {ROLE_NAMES_RU.get(invite['role'], invite['role'])}.",
            )
            return

    try:
        topic = await context.bot.create_forum_topic(
            chat_id=GROUP_CHAT_ID,
            name=f"Ученик {user.full_name}",
        )
    except Exception as e:
        logger.error(f"Не удалось создать тему для {user.id}: {e}")
        await message.reply_text(
            "⚠️ Не удалось создать комнату. Попробуйте ещё раз чуть позже "
            "или сообщите администратору."
        )
        return

    room_id = storage.create_room(topic.message_thread_id, name=f"Ученик {user.full_name}", created_by=user.id)
    storage.upsert_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=ROLE_STUDENT,
        room_id=room_id,
    )

    await message.reply_text(
        "👋 Добро пожаловать! Ваша комната создана.\n\n"
        "Пишите сюда сообщения — учителя увидят их без вашего имени и аккаунта.\n\n"
        "Чтобы добавить родителя в эту комнату, отправьте:\n"
        "/add_parent @username\n"
        "или\n"
        "/add_parent 123456789 (Telegram ID)"
    )


# -------------------- /myrole --------------------

async def myrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = storage.get_user(user.id)
    if not row or not row["role"]:
        await update.message.reply_text("Вы ещё не зарегистрированы. Отправьте /start.")
        return
    await update.message.reply_text(f"Ваша роль: {ROLE_NAMES_RU.get(row['role'], row['role'])}.")


# -------------------- /setrole (админ) --------------------

async def setrole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Команда доступна только администратору.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Использование: /setrole <user_id> <student|parent|teacher>")
        return

    target_id_raw, role = context.args
    role = role.lower()
    if role not in (ROLE_STUDENT, ROLE_PARENT, ROLE_TEACHER):
        await update.message.reply_text("Роль должна быть одной из: student, parent, teacher.")
        return
    try:
        target_id = int(target_id_raw)
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return

    target = storage.get_user(target_id)
    if not target:
        await update.message.reply_text("Пользователь ещё не запускал бота (нет в базе).")
        return

    storage.set_role(target_id, role)
    await update.message.reply_text(f"✅ Роль пользователя {target_id} изменена на {role}.")


# -------------------- /add_parent --------------------

async def add_parent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    caller = storage.get_user(user.id)

    if not caller or not caller["room_id"] or caller["role"] not in (ROLE_STUDENT, ROLE_PARENT):
        await update.message.reply_text(
            "Добавлять родителей может только ученик или уже добавленный родитель, "
            "состоящий в комнате."
        )
        return

    if not context.args:
        await update.message.reply_text("Использование: /add_parent @username  или  /add_parent 123456789")
        return

    identifier = context.args[0].lstrip("@")
    room_id = caller["room_id"]
    room = storage.get_room(room_id)

    target_user_id = None
    target_username = None
    if identifier.isdigit():
        target_user_id = int(identifier)
    else:
        target_username = identifier

    existing_target = None
    if target_user_id:
        existing_target = storage.get_user(target_user_id)
    elif target_username:
        existing_target = storage.find_user_by_username(target_username)

    if existing_target:
        storage.upsert_user(
            user_id=existing_target["user_id"],
            role=ROLE_PARENT,
            room_id=room_id,
        )
        try:
            await context.bot.send_message(
                chat_id=existing_target["user_id"],
                text=(
                    f"✅ Вы добавлены в комнату «{room['name']}» как родитель.\n"
                    "Теперь все сообщения из этой комнаты будут приходить сюда."
                ),
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить {existing_target['user_id']}: {e}")
        await update.message.reply_text("✅ Родитель добавлен в комнату.")
        return

    storage.add_pending_invite(
        room_id=room_id,
        role=ROLE_PARENT,
        invited_by=user.id,
        target_user_id=target_user_id,
        target_username=target_username,
    )
    await update.message.reply_text(
        "📝 Приглашение сохранено. Как только этот человек напишет боту команду "
        "/start, он автоматически присоединится к вашей комнате."
    )


# -------------------- /add_teacher (админ) --------------------

async def add_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Команда доступна только администратору.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /add_teacher <user_id>")
        return

    try:
        target_id = int(context.args[0].lstrip("@"))
    except ValueError:
        await update.message.reply_text("Укажите числовой Telegram ID преподавателя.")
        return

    existing = storage.get_user(target_id)
    if existing:
        storage.set_role(target_id, ROLE_TEACHER)
    else:
        storage.upsert_user(user_id=target_id, role=ROLE_TEACHER)

    await update.message.reply_text(
        f"✅ Пользователь {target_id} назначен преподавателем. "
        "Он должен быть участником группы, чтобы отвечать в темах."
    )


# -------------------- уведомление комнаты --------------------

async def notify_room(context, room_id: int, exclude_user_id: int, text: str):
    for member in storage.get_room_members(room_id):
        if member["user_id"] == exclude_user_id:
            continue
        try:
            await context.bot.send_message(chat_id=member["user_id"], text=text)
        except Exception as e:
            logger.warning(f"Не удалось уведомить {member['user_id']}: {e}")


# -------------------- рассылка всем участникам комнаты --------------------

async def broadcast_to_room(context, room_id: int, sender_id: int, text: str, role: str):
    """Отправляет сообщение всем участникам комнаты, кроме отправителя, с пометкой роли."""
    members = storage.get_room_members(room_id)
    role_ru = ROLE_NAMES_RU.get(role, role).capitalize()
    for member in members:
        if member["user_id"] == sender_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=member["user_id"],
                text=f"📩 {role_ru}:\n{text}"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение участнику {member['user_id']}: {e}")


# -------------------- безопасная отправка в тему (восстановление) --------------------

async def send_to_thread_safe(context, chat_id, thread_id, text, user, room_id):
    try:
        await context.bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text=text)
        return thread_id
    except Exception as e:
        if "Message thread not found" in str(e):
            logger.warning(f"Тема {thread_id} не найдена. Создаём новую для комнаты {room_id}.")
            new_topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"Ученик {user.full_name} (восстановлена)",
            )
            new_thread_id = new_topic.message_thread_id
            storage.update_thread_id(room_id, new_thread_id)
            await context.bot.send_message(chat_id=chat_id, message_thread_id=new_thread_id, text=text)
            return new_thread_id
        else:
            raise


async def copy_to_thread_safe(context, from_chat_id, message_id, chat_id, thread_id, user, room_id):
    try:
        copied = await context.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            message_thread_id=thread_id,
        )
        return copied.message_id
    except Exception as e:
        if "Message thread not found" in str(e):
            logger.warning(f"Тема {thread_id} не найдена при копировании. Создаём новую для комнаты {room_id}.")
            new_topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"Ученик {user.full_name} (восстановлена)",
            )
            new_thread_id = new_topic.message_thread_id
            storage.update_thread_id(room_id, new_thread_id)
            copied = await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
                message_thread_id=new_thread_id,
            )
            return copied.message_id
        else:
            raise


# -------------------- пересылка: пользователь -> тема + рассылка всем участникам --------------------

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    row = storage.get_user(user.id)
    if not row or not row["room_id"]:
        await message.reply_text("Сначала отправьте /start, чтобы создать или найти вашу комнату.")
        return

    room = storage.get_room(row["room_id"])
    if room is None:
        storage.clear_user_room(user.id)
        await message.reply_text("Ваша комната была удалена. Отправьте /start, чтобы создать новую.")
        return

    thread_id = room["thread_id"]
    role = row["role"] or ROLE_STUDENT

    # 1. Отправляем в группу учителей (с восстановлением, если тема удалена)
    try:
        new_thread_id = await send_to_thread_safe(
            context,
            GROUP_CHAT_ID,
            thread_id,
            f"📩 Сообщение от {role_label(role)}:",
            user,
            row["room_id"],
        )
        thread_id = new_thread_id
    except Exception as e:
        logger.error(f"Не удалось отправить заголовок: {e}")
        await message.reply_text("⚠️ Не удалось отправить сообщение. Попробуйте ещё раз.")
        return

    try:
        copied_id = await copy_to_thread_safe(
            context,
            message.chat.id,
            message.message_id,
            GROUP_CHAT_ID,
            thread_id,
            user,
            row["room_id"],
        )
        storage.save_message_map(copied_id, thread_id, user.id)
    except Exception as e:
        logger.error(f"Ошибка copy_message: {e}")
        await message.reply_text("⚠️ Не удалось отправить сообщение. Попробуйте ещё раз.")
        return

    # 2. Рассылаем всем участникам комнаты (кроме отправителя) с пометкой роли
    await broadcast_to_room(context, row["room_id"], user.id, message.text, role)


# -------------------- пересылка: ответ в теме -> всем участникам комнаты --------------------

async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id or not message.reply_to_message:
        return

    thread_id = message.message_thread_id
    room = storage.get_room_by_thread(thread_id)
    if not room:
        logger.warning(f"Не найдена комната для thread_id {thread_id}")
        return

    members = storage.get_room_members(room["room_id"])
    teacher_id = update.effective_user.id

    for member in members:
        if member["user_id"] == teacher_id:
            continue
        try:
            await context.bot.copy_message(
                chat_id=member["user_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except Exception as e:
            logger.warning(f"Не удалось переслать ответ участнику {member['user_id']}: {e}")


def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myrole", myrole))
    application.add_handler(CommandHandler("setrole", setrole))
    application.add_handler(CommandHandler("add_parent", add_parent))
    application.add_handler(CommandHandler("add_teacher", add_teacher))

    application.add_handler(
        MessageHandler(
            ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_private_message,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.ChatType.SUPERGROUP & filters.REPLY,
            handle_group_reply,
        )
    )

    logger.info("🤖 Бот запущен (общий чат для комнаты + восстановление тем)")
    application.run_polling()


if __name__ == "__main__":
    main()
