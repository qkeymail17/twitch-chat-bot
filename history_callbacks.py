from telegram import Update
from telegram.ext import ContextTypes
import database as db
from ui import CB_UI_HISTORY, CB_HIST_PAGE, CB_HIST_VOD_PREFIX
from history_view import _send_history_cards


async def ui_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    user_id = update.effective_user.id

    if data == CB_UI_HISTORY:
        items = db.get_history_for_user(user_id, limit=10, offset=0)
        if not items:
            await q.message.reply_text("История пуста.")
            return

        await _send_history_cards(q.message.chat_id, context, items, page=0)
        return


async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith(CB_HIST_PAGE):
        return
    try:
        page = int(data[len(CB_HIST_PAGE):])
    except ValueError:
        return

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    if not items:
        await q.message.reply_text("История пуста.")
        return

    await _send_history_cards(q.message.chat_id, context, items, page)


async def history_vod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith(CB_HIST_VOD_PREFIX):
        return

    try:
        idx = int(data[len(CB_HIST_VOD_PREFIX):])
    except ValueError:
        return

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    if idx < 0 or idx >= len(items):
        await q.message.reply_text("Запрос не найден.")
        return

    vod_url = items[idx].get("vod_url")
    if not vod_url:
        await q.message.reply_text("Ссылка не найдена.")
        return

    await q.message.reply_text(f"<code>{vod_url}</code>", parse_mode="HTML")