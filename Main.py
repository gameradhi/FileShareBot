import os
import json
import random
import string
import telebot

# ========= CONFIG =========
TOKEN = os.getenv("BOT_TOKEN")  # will come from Replit Secret

if not TOKEN:
    raise ValueError("BOT_TOKEN is not set")

bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 8545081401               # your admin id
ADMIN_USERNAME = "@AntManIndia"
STORAGE_CHANNEL_ID = -1003477298276 # your storage channel id

DB_FILE = "batches.json"
# ==========================


def load_db():
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))


@bot.message_handler(commands=['start'])
def start_handler(message):
    parts = message.text.strip().split(maxsplit=1)

    # /start with NO code
    if len(parts) == 1:
        text = (
            "👋 Welcome to the File Share Bot.\n\n"
            "Send a special link like this to access files:\n"
            "`https://t.me/sodasarbathbot?start=<code>`\n\n"
            "If you are the admin, send any file here to generate a link."
        )
        bot.reply_to(message, text, parse_mode="Markdown")
        return

    # /start <code>
    code = parts[1].strip()
    db = load_db()

    batch = db.get(code)
    if not batch:
        bot.reply_to(message, "❌ This link is invalid.")
        return

    if batch.get("used", False):
        bot.reply_to(message, "⚠️ This link has already been used and is now expired.")
        return

    # send all files from storage channel
    msg_ids = batch.get("msg_ids", [])
    if not msg_ids:
        bot.reply_to(message, "⚠️ No files found for this link. Contact admin.")
        return

    for mid in msg_ids:
        try:
            bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=mid,
                protect_content=True  # non-forwardable
            )
        except Exception as e:
            print("Error sending file:", e)

    # mark as used (global one-time link)
    batch["used"] = True
    batch["used_by"] = message.from_user.id
    db[code] = batch
    save_db(db)


@bot.message_handler(commands=['myid'])
def myid_handler(message):
    bot.reply_to(message, f"Your Telegram ID: `{message.from_user.id}`", parse_mode="Markdown")


@bot.message_handler(content_types=[
    'document', 'video', 'audio', 'photo', 'animation', 'voice'
])
def admin_upload_handler(message):
    """Admin sends/forwards one or many files → bot saves them and returns a link."""
    if message.from_user.id != ADMIN_ID:
        # ignore non-admin uploads
        return

    db = load_db()

    # For grouping multiple files sent as album, use media_group_id
    group_id = message.media_group_id  # can be None
    if group_id is not None:
        group_key = f"group_{group_id}"
    else:
        group_key = f"single_{message.message_id}"

    # If this groupKey seen first time → create new batch code
    if group_key not in db:
        code = generate_code()
        db[group_key] = {
            "code": code,
            "msg_ids": [],
        }
        save_db(db)
    else:
        code = db[group_key]["code"]

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

    # append message id to this batch
    db = load_db()
    batch = db.get(group_key, {"code": code, "msg_ids": []})
    batch["msg_ids"].append(channel_msg_id)
    db[group_key] = batch
    save_db(db)

    # reply with link only once per batch (first file)
    if len(batch["msg_ids"]) == 1:
        deep_link = f"https://t.me/sodasarbathbot?start={code}"
        text = (
            "✅ Files saved.\n\n"
            "Here is your one-time link for this batch:\n"
            f"`{deep_link}`\n\n"
            "Anyone who opens this link will receive all files in this batch, "
            "and then the link will expire."
        )
        bot.reply_to(message, text, parse_mode="Markdown")
    else:
        # optional: just confirm added to same batch
        bot.reply_to(message, "➕ Added to the same batch.")


@bot.message_handler(commands=['adminbatches'])
def admin_list_batches(message):
    """Admin command: show raw info for debugging."""
    if message.from_user.id != ADMIN_ID:
        return
    db = load_db()
    text = "📦 Batches (debug view):\n\n"
    for key, value in db.items():
        if key.startswith("group_") or key.startswith("single_"):
            text += f"- {key} → code `{value['code']}`, files: {len(value['msg_ids'])}\n"
    if text.strip() == "📦 Batches (debug view):":
        text += "No batches yet."
    bot.reply_to(message, text, parse_mode="Markdown")


print("Bot starting…")
bot.infinity_polling(skip_pending=True)
