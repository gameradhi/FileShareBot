import os
import json
import random
import string
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========= CONFIG =========
TOKEN = os.getenv("BOT_TOKEN")  # from Replit Secret
 
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 8545081401               # your admin id
ADMIN_USERNAME = "@AntManIndia"
STORAGE_CHANNEL_ID = -1003477298276 # your storage channel id
DB_FILE = "batches.json"
# ==========================

# in-memory group -> code mapping for album batches
ACTIVE_GROUP_CODES = {}


def load_db():
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                return {}
    except Exception:
        return {}


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def get_display_name(user):
    if getattr(user, "username", None):
        return f"@{user.username}"
    if getattr(user, "first_name", None) or getattr(user, "last_name", None):
        return (user.first_name or "") + (" " + user.last_name if getattr(user, "last_name", None) else "")
    return "there"


# ========== /start ==========

@bot.message_handler(commands=['start'])
def start_handler(message):
    parts = message.text.strip().split(maxsplit=1)
    user = message.from_user
    name = get_display_name(user)
    is_admin = (user.id == ADMIN_ID)

    # /start with NO code
    if len(parts) == 1:
        if is_admin:
            text = (
                f"👋 Hey {name} (Admin)\n\n"
                "This is your file link generator bot.\n\n"
                "🔹 Just send or forward files here.\n"
                "🔹 If you send multiple files as an album, one batch link is created.\n"
                "🔹 Each link works globally ONE TIME only.\n\n"
                "Commands:\n"
                "• /admin – Open admin panel\n"
                "• /info <code> – Details about a code\n"
                "• /revoke <code> – Manually expire a code\n"
                "• /name <code> <title> – Set batch title\n"
                "• /note <code> <text> – Set internal note\n"
                "• /myid – Show your Telegram ID\n"
            )
        else:
            text = (
                f"👋 Hey {name}!\n\n"
                "This bot delivers private files using one-time links.\n\n"
                "👉 If you already have a link, just tap it.\n"
                "If this link shows as expired, ask the seller/creator for a new link.\n"
            )
        bot.reply_to(message, text)
        return

    # /start <code>
    code = parts[1].strip()
    db = load_db()

    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ This link is invalid or expired.\nAsk the seller for a new one.")
        return

    if batch.get("used", False):
        used_by = batch.get("used_by_username") or batch.get("used_by")
        msg = "⚠️ This link has already been used and is now expired."
        if used_by:
            msg += f"\nUsed by: {used_by}"
        bot.reply_to(message, msg)
        return

    msg_ids = batch.get("msg_ids", [])
    if not msg_ids:
        bot.reply_to(message, "⚠️ No files found for this link. Contact admin.")
        return

    # send all files from storage channel (non-forwardable)
    for mid in msg_ids:
        try:
            bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=mid,
                protect_content=True
            )
        except Exception as e:
            print("Error sending file:", e)

    # mark as used (global one-time)
    batch["used"] = True
    batch["used_by"] = message.from_user.id
    batch["used_by_username"] = get_display_name(message.from_user)
    batch["used_at"] = int(time.time())
    db[code] = batch
    save_db(db)


# ========== Helper: stats ==========

def compute_stats(db):
    total_batches = len(db)
    used_count = 0
    users = set()
    for code, b in db.items():
        if b.get("used"):
            used_count += 1
            if b.get("used_by"):
                users.add(b["used_by"])
    return total_batches, used_count, len(users)


# ========== /myid ==========

@bot.message_handler(commands=['myid'])
def myid_handler(message):
    bot.reply_to(message, f"Your Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


# ========== ADMIN UPLOAD (create batches) ==========

@bot.message_handler(content_types=['document', 'video', 'audio', 'photo', 'animation', 'voice'])
def admin_upload_handler(message):
    """Admin sends/forwards one or many files → bot saves them and returns a link."""
    if message.from_user.id != ADMIN_ID:
        # ignore non-admin uploads
        return

    db = load_db()

    group_id = message.media_group_id
    code = None

    if group_id is not None:
        # album / multiple files in one group
        if group_id in ACTIVE_GROUP_CODES:
            code = ACTIVE_GROUP_CODES[group_id]
        else:
            code = generate_code()
            ACTIVE_GROUP_CODES[group_id] = code
    else:
        # single file → own code
        code = generate_code()
        while code in db:
            code = generate_code()

    # initialize batch if first time
    if code not in db:
        db[code] = {
            "msg_ids": [],
            "used": False,
            "used_by": None,
            "used_by_username": None,
            "used_at": None,
            "created_at": int(time.time()),
            "name": None,
            "note": None,
        }

    # copy incoming message to storage channel
    try:
        copied = bot.copy_message(
            chat_id=STORAGE_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        channel_msg_id = copied.message_id
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to copy to storage channel.\n{e}")
        return

    # append msg id
    batch = db[code]
    batch["msg_ids"].append(channel_msg_id)
    db[code] = batch
    save_db(db)

    # if first file in this batch → send the link
    if len(batch["msg_ids"]) == 1:
        deep_link = f"https://t.me/sodasarbathbot?start={code}"
        title = batch.get("name") or "(no title yet)"
        text = (
            "✅ Batch created.\n\n"
            f"Title: *{title}*\n"
            "Here is your ONE-TIME link for this batch:\n"
            f"`{deep_link}`\n\n"
            "Anyone who opens this link will receive all files in this batch, "
            "and then the link will expire globally.\n\n"
            f"💡 You can set a nicer title later with:\n`/name {code} Your Title`"
        )
        bot.reply_to(message, text, parse_mode="Markdown")
    else:
        bot.reply_to(message, f"➕ Added to existing batch with code `{code}`.", parse_mode="Markdown")


# ========== /admin panel ==========

@bot.message_handler(commands=['admin'])
def admin_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📦 Last batches", callback_data="admin_last"))
    kb.add(InlineKeyboardButton("📊 Stats", callback_data="admin_stats"))

    text = (
        f"👑 Admin Panel – {ADMIN_USERNAME}\n\n"
        "Choose an option below:"
    )
    bot.reply_to(message, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_"))
def admin_callbacks(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Not allowed.")
        return

    db = load_db()

    if call.data == "admin_last":
        if not db:
            bot.answer_callback_query(call.id, "No batches yet.")
            bot.edit_message_text(
                "📦 No batches created yet.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            return

        # sort by created_at desc, fallback to 0
        items = []
        for code, b in db.items():
            created = b.get("created_at", 0)
            items.append((code, b, created))
        items.sort(key=lambda x: x[2], reverse=True)
        items = items[:10]

        lines = ["📦 Last batches:\n"]
        for code, b, created in items:
            status = "USED" if b.get("used") else "UNUSED"
            count = len(b.get("msg_ids", []))
            title = b.get("name") or "(no title)"
            lines.append(f"• `{code}` – {count} files – *{status}* – {title}")
        text = "\n".join(lines)
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, "Last batches shown.")
    elif call.data == "admin_stats":
        total_batches, used_count, unique_users = compute_stats(db)
        text = (
            "📊 Stats:\n\n"
            f"• Total batches: {total_batches}\n"
            f"• Used links: {used_count}\n"
            f"• Unique users: {unique_users}\n"
        )
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id, "Stats updated.")


# ========== /info and /revoke ==========

@bot.message_handler(commands=['info'])
def info_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/info <code>`", parse_mode="Markdown")
        return

    code = parts[1].strip()
    db = load_db()
    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ No batch found for that code.")
        return

    count = len(batch.get("msg_ids", []))
    used = batch.get("used", False)
    used_by = batch.get("used_by_username") or batch.get("used_by") or "–"
    created_at = batch.get("created_at")
    used_at = batch.get("used_at")
    name = batch.get("name") or "(no title)"
    note = batch.get("note") or "–"

    def fmt_ts(ts):
        if not ts:
            return "–"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    text = (
        f"ℹ️ Info for code `{code}`:\n\n"
        f"• Title: *{name}*\n"
        f"• Note: {note}\n"
        f"• Files: {count}\n"
        f"• Used: {'YES' if used else 'NO'}\n"
        f"• Used by: {used_by}\n"
        f"• Created at: {fmt_ts(created_at)}\n"
        f"• Used at: {fmt_ts(used_at)}\n"
    )
    bot.reply_to(message, text, parse_mode="Markdown")


@bot.message_handler(commands=['revoke'])
def revoke_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/revoke <code>`", parse_mode="Markdown")
        return

    code = parts[1].strip()
    db = load_db()
    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ No batch found for that code.")
        return

    batch["used"] = True
    batch["used_by"] = None
    batch["used_by_username"] = "revoked"
    batch["used_at"] = int(time.time())
    db[code] = batch
    save_db(db)

    bot.reply_to(message, f"🚫 Code `{code}` has been revoked.", parse_mode="Markdown")


# ========== /name and /note for Phase 2 ==========

@bot.message_handler(commands=['name'])
def name_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: `/name <code> <title>`", parse_mode="Markdown")
        return

    code = parts[1].strip()
    title = parts[2].strip()

    db = load_db()
    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ No batch found for that code.")
        return

    batch["name"] = title
    db[code] = batch
    save_db(db)

    bot.reply_to(message, f"✅ Title for `{code}` set to *{title}*.", parse_mode="Markdown")


@bot.message_handler(commands=['note'])
def note_handler(message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: `/note <code> <text>`", parse_mode="Markdown")
        return

    code = parts[1].strip()
    note = parts[2].strip()

    db = load_db()
    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ No batch found for that code.")
        return

    batch["note"] = note
    db[code] = batch
    save_db(db)

    bot.reply_to(message, f"📝 Note for `{code}` updated.", parse_mode="Markdown")


print("Bot starting…")
bot.infinity_polling(skip_pending=True)
