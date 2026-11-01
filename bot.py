import asyncio
import logging
import os
import re
import tempfile
import uuid
from pathlib import Path

import yt_dlp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("9178832191:AAFDnA6pRWGhGOIZHhwNHb1kqfPPvnoW5Uo")  # ដាក់ token ពី @BotFather
MAX_SIZE = 50 * 1024 * 1024  # ដែនកំណត់ Bot API: 50MB
URL_RE = re.compile(r"https?://\S+")


# ---------- yt-dlp helpers (ដំណើរការក្នុង thread) ----------
def fetch_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
        return ydl.extract_info(url, download=False)


def fetch_media(url: str, mode: str, outdir: str) -> Path:
    opts = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": f"{outdir}/%(id)s.%(ext)s",
    }
    if mode == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        # ព្យាយាមយក mp4 ដែលតូចជាង 50MB
        opts["format"] = (
            "best[ext=mp4][filesize<50M]/best[ext=mp4][filesize_approx<50M]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        )
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    files = sorted(Path(outdir).iterdir(), key=lambda p: p.stat().st_mtime)
    if not files:
        raise RuntimeError("រកមិនឃើញឯកសារ")
    return files[-1]


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "សួស្តី! ផ្ញើ link ពី TikTok, Facebook, Instagram, YouTube, X ។ល។ មកខ្ញុំ "
        "ហើយជ្រើសរើស MP4 / MP3 / Caption។"
    )


async def on_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    match = URL_RE.search(update.message.text or "")
    if not match:
        return
    key = uuid.uuid4().hex[:8]
    context.user_data[key] = match.group(0)
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎬 MP4", callback_data=f"mp4|{key}"),
                InlineKeyboardButton("🎵 MP3", callback_data=f"mp3|{key}"),
                InlineKeyboardButton("📝 Caption", callback_data=f"cap|{key}"),
            ]
        ]
    )
    await update.message.reply_text("ជ្រើសរើសអ្វីដែលចង់បាន៖", reply_markup=kb)


async def on_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mode, key = q.data.split("|")
    url = context.user_data.get(key)
    if not url:
        await q.edit_message_text("Link ផុតសុពលភាព សូមផ្ញើម្តងទៀត។")
        return

    await q.edit_message_text("⏳ កំពុងដំណើរការ...")
    chat = q.message.chat_id

    try:
        if mode == "cap":
            info = await asyncio.to_thread(fetch_info, url)
            text = info.get("description") or info.get("title") or "(គ្មាន caption)"
            for i in range(0, len(text), 4000):
                await context.bot.send_message(chat, text[i : i + 4000])
            await q.edit_message_text("✅ រួចរាល់")
            return

        with tempfile.TemporaryDirectory() as tmp:
            path = await asyncio.to_thread(fetch_media, url, mode, tmp)
            if path.stat().st_size > MAX_SIZE:
                await q.edit_message_text(
                    "❌ ឯកសារធំជាង 50MB (ដែនកំណត់ Telegram Bot API)។"
                )
                return
            with open(path, "rb") as f:
                if mode == "mp3":
                    await context.bot.send_audio(chat, f)
                else:
                    await context.bot.send_video(chat, f, supports_streaming=True)

            # ផ្ញើ caption មកជាមួយដែរ
            try:
                info = await asyncio.to_thread(fetch_info, url)
                text = info.get("description") or info.get("title")
                if text:
                    await context.bot.send_message(chat, text[:4000])
            except Exception:
                pass
        await q.edit_message_text("✅ រួចរាល់")
    except Exception as e:
        logging.exception("download failed")
        await q.edit_message_text(f"❌ បរាជ័យ៖ {str(e)[:200]}")


def main():
    if not TOKEN:
        raise SystemExit("សូមកំណត់ BOT_TOKEN ជាមុន")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_link))
    app.add_handler(CallbackQueryHandler(on_choice))
    app.run_polling()


if __name__ == "__main__":
    main()
