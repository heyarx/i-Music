import os
import asyncio
import yt_dlp
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ChatAction

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://i-music.onrender.com/webhook
DOWNLOAD_FOLDER = "downloads/"
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")  # use Render env var or default

# Ensure downloads folder exists
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

app = FastAPI()
user_state = {}  # track user selections

# 21 Languages
languages = [
    "English","Hindi","Spanish","French","German","Italian","Japanese",
    "Korean","Chinese","Portuguese","Russian","Arabic","Bengali","Turkish",
    "Vietnamese","Thai","Malay","Swahili","Dutch","Greek","Hebrew"
]

formats = ["Audio","Video"]

# ---------------- BOT HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(lang, callback_data=f"lang_{lang}")] for lang in languages]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎵 Welcome! Choose your language:", reply_markup=reply_markup)

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    user_state[query.from_user.id] = {"language": lang}
    keyboard = [[InlineKeyboardButton(fmt, callback_data=f"fmt_{fmt}")] for fmt in formats]
    await query.edit_message_text(text=f"Language selected: {lang}\nChoose format:", reply_markup=InlineKeyboardMarkup(keyboard))

async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fmt = query.data.split("_")[1]
    user_state[query.from_user.id]["format"] = fmt
    await query.edit_message_text(text=f"Format selected: {fmt}\nSend me the song name:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_state or "format" not in user_state[user_id]:
        await update.message.reply_text("Please start with /start first!")
        return

    song_name = update.message.text
    fmt = user_state[user_id]["format"].lower()  # audio or video

    status_msg = await update.message.reply_text(f"Preparing to download '{song_name}' as {fmt}... 🎵")

    # ---------------- YT_DLP OPTIONS ----------------
    ydl_opts = {
        "format": "bestaudio/best" if fmt=="audio" else "bestvideo+bestaudio",
        "outtmpl": f"{DOWNLOAD_FOLDER}/{song_name}.%(ext)s",
        "noplaylist": True,
        "quiet": True,
    }

    # Use cookies if available
    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    else:
        await update.message.reply_text(
            f"⚠️ Cookies file not found at '{COOKIES_FILE}'. "
            "Some YouTube videos may fail to download."
        )

    loop = asyncio.get_event_loop()
    file_path = None

    def download():
        nonlocal file_path
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{song_name}", download=True)
                file_path = ydl.prepare_filename(info['entries'][0] if 'entries' in info else info)
        except Exception as e:
            print(f"Download error: {e}")

    # ---------------- Typing + Progress Animation ----------------
    async def typing_animation():
        dots = 0
        while not download_task.done():
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
            dots = (dots + 1) % 4
            await status_msg.edit_text(f"Downloading '{song_name}' as {fmt}... {'•'*dots}")
            await asyncio.sleep(1)

    download_task = loop.run_in_executor(None, download)
    animation_task = asyncio.create_task(typing_animation())
    await download_task
    animation_task.cancel()

    # ---------------- Send File ----------------
    if file_path and os.path.exists(file_path):
        await update.message.reply_document(InputFile(file_path))
        os.remove(file_path)
    else:
        await update.message.reply_text("❌ Failed to download the song!")

# ---------------- TELEGRAM APP ----------------
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(language_choice, pattern=r"^lang_"))
bot_app.add_handler(CallbackQueryHandler(format_choice, pattern=r"^fmt_"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ---------------- FASTAPI STARTUP ----------------
@app.on_event("startup")
async def startup():
    # Set webhook
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    # Initialize bot & start processing updates
    await bot_app.initialize()
    asyncio.create_task(bot_app.start())

# ---------------- FASTAPI WEBHOOK ----------------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"ok": True}

# ---------------- HEALTH CHECK ----------------
@app.get("/")
async def root():
    return {"status": "Bot is running ✅"}
