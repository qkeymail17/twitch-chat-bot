from telegram import Update
from telegram.ext import ContextTypes
import database as db
from ui import CB_UI_HISTORY, CB_HIST_PAGE, CB_HIST_VOD_PREFIX
from history_view import send_history_message
from ui_history import build_history_message


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

        await send_history_message(q.message.chat_id, context, items, page=0)
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

    text, kb = build_history_message(items, page=page)
    await q.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )


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