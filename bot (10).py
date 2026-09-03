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
    """Родительный падеж для фразы 'Сообщение от ...' (Ученика/Родителя/Преподавателя)."""
    return ROLE_LABELS_RU.get(role, "Участника")


# -------------------- /start --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message

    existing = storage.get_user(user.id)

    if existing and existing["room_id"]:
        room = storage.get_room(existing["room_id"])
        if room is None:
            # Комната пропала (например, тему удалили руками) — отвязываем и даём создать новую.
            storage.clear_user_room(user.id)
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
                "Теперь ваши сообщения будут пересылаться в эту комнату."
            )
            await notify_room(
                context,
                room["room_id"],
                exclude_user_id=user.id,
                text=(
                    f"ℹ️ К комнате «{room['name']}» присоединился ещё один "
                    f"{ROLE_NAMES_RU.get(invite['role'], invite['role'])}."
                ),
            )
            return

    # Новый пользователь без приглашения — создаём новую комнату, роль по умолчанию "ученик".
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

    room_id = storage.create_room(
        topic.message_thread_id, name=f"Ученик {user.full_name}", created_by=user.id
    )
    storage.upsert_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=ROLE_STUDENT,
        room_id=room_id,
    )

    await message.reply_text(
        "👋 Добро пожаловать! Ваша комната создана.\n\n"
        "Пишите сюда сообщения — учителя увидят их без вашего имени и аккаунта. "
        "Если позже вы добавите в комнату родителя, вся переписка будет видна всем "
        "участникам комнаты (ученику, родителям и учителю) — но не ваш Telegram ID и не имя.\n\n"
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
        await update.message.reply_text("Использование: /add_parent @username или /add_parent 123456789")
        return

    identifier = context.args[0].lstrip("@")
    room_id = caller["room_id"]
    room = storage.get_room(room_id)

    target_user_id = None
    target_username = None
    if identifier.isdigit():
        target_user_id = int(identifier)
        if target_user_id == user.id:
            await update.message.reply_text("Нельзя добавить самого себя.")
            return
    else:
        target_username = identifier

    existing_target = None
    if target_user_id:
        existing_target = storage.get_user(target_user_id)
    elif target_username:
        existing_target = storage.find_user_by_username(target_username)
        if existing_target and existing_target["user_id"] == user.id:
            await update.message.reply_text("Нельзя добавить самого себя.")
            return

    if existing_target:
        if existing_target["room_id"] == room_id:
            await update.message.reply_text("Этот пользователь уже состоит в вашей комнате.")
            return

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
                    "Теперь ваши сообщения будут пересылаться в эту комнату."
                ),
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить {existing_target['user_id']}: {e}")

        await notify_room(
            context,
            room_id,
            exclude_user_id=existing_target["user_id"],
            text=f"ℹ️ К комнате «{room['name']}» присоединился ещё один родитель.",
        )
        await update.message.reply_text("✅ Родитель добавлен в комнату.")
        return

    # Ещё не писал боту — оставляем отложенное приглашение до его /start.
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


# -------------------- служебные уведомления комнате --------------------
async def notify_room(context, room_id: int, exclude_user_id: int, text: str):
    for member in storage.get_room_members(room_id):
        if member["user_id"] == exclude_user_id:
            continue
        try:
            await context.bot.send_message(chat_id=member["user_id"], text=text)
        except Exception as e:
            logger.warning(f"Не удалось уведомить {member['user_id']}: {e}")


async def broadcast_copy_to_room(
    context,
    room_id: int,
    exclude_user_id,
    role: str,
    from_chat_id: int,
    message_id: int,
    text_content: str = None,
):
    """Рассылает сообщение всем участникам комнаты, кроме exclude_user_id.
    Для текстовых сообщений — одним сообщением с жирной ролью и текстом.
    Для медиа — подпись отдельно, потом копия медиа."""
    members = storage.get_room_members(room_id)
    role_display = ROLE_NAMES_RU.get(role, role).capitalize()

    for member in members:
        if member["user_id"] == exclude_user_id:
            continue
        try:
            if text_content:
                # Текстовое сообщение – отправляем одним сообщением
                await context.bot.send_message(
                    chat_id=member["user_id"],
                    text=f"*{role_display}*\n{text_content}",
                    parse_mode="Markdown"
                )
            else:
                # Медиа без текста – подпись отдельно, потом копия медиа
                await context.bot.send_message(
                    chat_id=member["user_id"],
                    text=f"*{role_display}*",
                    parse_mode="Markdown"
                )
                await context.bot.copy_message(
                    chat_id=member["user_id"],
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение участнику {member['user_id']}: {e}")


# -------------------- пересылка: пользователь -> тема --------------------
async def _send_to_topic(context, thread_id: int, role: str, message):
    """Отправляет сообщение в тему группы учителей.
    Для текстовых сообщений — одним сообщением с ролью, выделенной жирным.
    Для медиа — сначала подпись, потом копия медиа."""
    # Если есть текст (или подпись у медиа), отправляем вместе
    text_content = message.text or message.caption
    if text_content:
        # Формируем одно сообщение: жирная роль, затем текст
        role_display = ROLE_NAMES_RU.get(role, role).capitalize()
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=thread_id,
            text=f"*{role_display}*\n{text_content}",
            parse_mode="Markdown"
        )
        # Для медиа с текстом – копировать само медиа не нужно, т.к. текст уже отправлен.
        # Если нужно сохранить медиа, можно дополнительно скопировать, но тогда будет дубль.
        # Поэтому возвращаем "пустое" сообщение для map? Можно вернуть None.
        return None
    else:
        # Только медиа (фото, видео, файл) – отправляем подпись и копируем медиа
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=thread_id,
            text=f"*{ROLE_NAMES_RU.get(role, role).capitalize()}*",
            parse_mode="Markdown"
        )
        return await context.bot.copy_message(
            chat_id=GROUP_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id,
        )    


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
    label = f"📩 Сообщение от {role_label(role)}:"

    try:
        copied = await _send_to_topic(context, thread_id, role, message)
        # Сейчас ответы рассылаются всем участникам комнаты, а не только автору,
        # так что этот лог не используется для маршрутизации — но пригодится,
        # если позже понадобится узнать, кто написал конкретное сообщение в теме.
        storage.save_message_map(copied.message_id, thread_id, user.id)
    except Exception as e:
        if "message thread not found" not in str(e).lower():
            logger.error(f"Ошибка отправки в тему {thread_id}: {e}")
            await message.reply_text("⚠️ Не удалось отправить сообщение. Попробуйте ещё раз.")
            return

        # Тема была удалена в группе руками — пересоздаём её для этой же комнаты
        # и обновляем thread_id, чтобы бот больше не "терял" эту комнату.
        logger.warning(f"Тема {thread_id} не найдена, пересоздаём для комнаты {room['room_id']}")
        try:
            new_topic = await context.bot.create_forum_topic(
                chat_id=GROUP_CHAT_ID,
                name=f"{room['name']} (восстановлена)",
            )
            thread_id = new_topic.message_thread_id
            storage.update_thread_id(room["room_id"], thread_id)

       copied = await _send_to_topic(context, thread_id, role, message)
# Если _send_to_topic вернула None (текстовое сообщение), то не сохраняем map
if copied:
    storage.save_message_map(copied.message_id, thread_id, user.id)

# Рассылка всем участникам (текст берём из message.text или message.caption)
text_content = message.text or message.caption
await broadcast_copy_to_room(
    context,
    room["room_id"],
    exclude_user_id=user.id,
    role=role,
    from_chat_id=message.chat.id,
    message_id=message.message_id,
    text_content=text_content,
)


# -------------------- пересылка: сообщение в теме -> всем участникам комнаты --------------------
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.message_thread_id:
        return

    sender = message.from_user
    # Критично: пропускаем сообщения самого бота (заголовки и копии, которые бот
    # только что сам отправил в тему) — иначе получится зацикливание: бот увидит
    # свою же скопированную копию и попытается разослать её снова.
    if sender is None or sender.is_bot:
        return

    thread_id = message.message_thread_id
    room = storage.get_room_by_thread(thread_id)
    if not room:
        # Сообщение в теме, которая не привязана ни к одной комнате (например,
        # служебная тема или тема, созданная не ботом) — игнорируем.
        return

    sender_row = storage.get_user(sender.id)
    # Тот, кто пишет прямо в группе и не зарегистрирован как ученик/родитель,
    # по умолчанию считается преподавателем.
    role = sender_row["role"] if sender_row and sender_row["role"] else ROLE_TEACHER
    label = f"📩 Сообщение от {role_label(role)}:"

text_content = message.text or message.caption
await broadcast_copy_to_room(
    context,
    room["room_id"],
    exclude_user_id=sender.id,
    role=role,
    from_chat_id=message.chat.id,
    message_id=message.message_id,
    text_content=text_content,
)


# -------------------- main --------------------
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
            filters.ChatType.SUPERGROUP,
            handle_group_message,
        )
    )

    logger.info("🤖 Бот запущен (SQLite + комнаты + роли + восстановление тем)")
    application.run_polling()


if __name__ == "__main__":
    main()
