from telegram import Update
from telegram.ext import ContextTypes

from ui import build_format_keyboard
from handlers_state import extract_vod_id_strict, is_busy, set_pending

import re

async def vod_link_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (update.message.text or "").strip()
    vod_id = extract_vod_id_strict(text)

    # fallback: ищем последнее длинное число в сообщении
    if not vod_id:
        matches = re.findall(r"\d{7,12}", text)
        if matches:
            vod_id = matches[-1]

    if not vod_id:
        return

    if is_busy(context):
        await update.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    vod_url = f"https://www.twitch.tv/videos/{vod_id}"
    set_pending(context, vod_url=vod_url, vod_id=vod_id)
    await update.message.reply_text("Выбери формат:", reply_markup=build_format_keyboard())