from telegram import Update
from telegram.ext import ContextTypes

from ui import build_format_keyboard
from handlers_state import extract_vod_id_strict, is_busy, set_pending


async def vod_link_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (update.message.text or "").strip()
    vod_id = extract_vod_id_strict(text)
    if not vod_id:
        return

    if is_busy(context):
        await update.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    set_pending(context, vod_url=text, vod_id=vod_id)
    await update.message.reply_text("Выбери формат:", reply_markup=build_format_keyboard())