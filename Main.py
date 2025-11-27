import os
import telebot

# We will set BOT_TOKEN in Railway, not hardcoded here
TOKEN = os.getenv("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 8545081401  # your admin user id

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Bot is running on Railway ✅")

bot.infinity_polling()
