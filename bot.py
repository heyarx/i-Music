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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DOWNLOAD_FOLDER = "downloads/"
COOKIES_FILE = os.getenv("COOKIES_FILE", "cookiex.txt")  # fallback

# Ensure downloads folder exists
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

app = FastAPI()
user_state = {}

languages = [
    "English","Hindi","Spanish","French","German","Italian","Japanese",
    "Korean","Chinese","Portuguese","Russian","Arabic","Bengali","Turkish",
    "Vietnamese","Thai","Malay","Swahili","Dutch","Greek","Hebrew"
]

formats = ["Audio","Video"]

language_flags = {
    "English": "🇬🇧", "Hindi": "🇮🇳", "Spanish": "🇪🇸", "French": "🇫🇷",
    "German": "🇩🇪", "Italian": "🇮🇹", "Japanese": "🇯🇵", "Korean": "🇰🇷",
    "Chinese": "🇨🇳", "Portuguese": "🇵🇹", "Russian": "🇷🇺", "Arabic": "🇸🇦",
    "Bengali": "🇧🇩", "Turkish": "🇹🇷", "Vietnamese": "🇻🇳", "Thai": "🇹🇭",
    "Malay": "🇲🇾", "Swahili": "🇰🇪", "Dutch": "🇳🇱", "Greek": "🇬🇷", "Hebrew": "🇮🇱"
}

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🎵 Welcome! Loading languages...")
    keyboard = []
    row = []
    for i, lang in enumerate(languages, 1):
        button = InlineKeyboardButton(f"{language_flags[lang]} {lang}", callback_data=f"lang_{lang}")
        row.append(button)
        if i % 3 == 0:
            keyboard.append(row)
            row = []
        # Animated effect: update every button dynamically
        await asyncio.sleep(0.1)
        await msg.edit_text(f"🎵 Loading languages... {i}/{len(languages)}")
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    await msg.edit_text("🎵 Please select your language:")
    await msg.edit_reply_markup(InlineKeyboardMarkup(keyboard))

# ---------------- LANGUAGE SELECTION ----------------
async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split("_")[1]
    if lang == "cancel":
        await query.edit_message_text("❌ Operation canceled.")
        return
    user_state[query.from_user.id] = {"language": lang}
    await show_format_menu(query)

async def show_format_menu(query):
    keyboard = [
        [
            InlineKeyboardButton("🎧 Audio", callback_data="fmt_Audio"),
            InlineKeyboardButton("🎬 Video", callback_data="fmt_Video")
        ],
        [InlineKeyboardButton("🔙 Back to Language", callback_data="back_language")]
    ]
    await query.edit_message_text(
        text=f"Language selected: {user_state[query.from_user.id]['language']}\nChoose format:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------- FORMAT SELECTION ----------------
async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fmt = query.data.split("_")[1]
    if fmt == "back":
        await start(query, context)
        return
    user_state[query.from_user.id]["format"] = fmt
    await query.edit_message_text(
        text=f"Format selected: {fmt}\nSend me the song name you want to download:"
    )

# ---------------- DOWNLOAD HANDLER ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in user_state or "format" not in user_state[user_id]:
        await update.message.reply_text("Please start with /start first!")
        return

    song_name = update.message.text
    fmt = user_state[user_id]["format"].lower()
    status_msg = await update.message.reply_text(f"Preparing to download '{song_name}' as {fmt}... 🎵")

    ydl_opts = {
        "format": "bestaudio/best" if fmt=="audio" else "bestvideo+bestaudio",
        "outtmpl": f"{DOWNLOAD_FOLDER}/{song_name}.%(ext)s",
        "noplaylist": True,
        "quiet": True,
    }

    # Force MP3 for audio
    if fmt == "audio":
        ydl_opts.update({
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
    else:
        await update.message.reply_text(f"⚠️ Cookies file not found at '{COOKIES_FILE}'.")

    loop = asyncio.get_event_loop()
    file_path = None

    def download():
        nonlocal file_path
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{song_name}", download=True)
                file_path = ydl.prepare_filename(info['entries'][0] if 'entries' in info else info)
                if fmt=="audio":
                    file_path = os.path.splitext(file_path)[0]+".mp3"
        except Exception as e:
            print(f"Download error: {e}")

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

    if file_path and os.path.exists(file_path):
        await update.message.reply_document(InputFile(file_path))
        os.remove(file_path)
    else:
        await update.message.reply_text("❌ Failed to download the song!")

# ---------------- TELEGRAM APP ----------------
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(language_choice, pattern=r"^lang_|^cancel$|^back_language$"))
bot_app.add_handler(CallbackQueryHandler(format_choice, pattern=r"^fmt_"))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ---------------- FASTAPI STARTUP ----------------
@app.on_event("startup")
async def startup():
    await bot_app.bot.set_webhook(WEBHOOK_URL)
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
