from telegram import Update
from telegram.ext import ContextTypes

from handlers_state import is_busy, set_cancel


async def pending_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if is_busy(context):
        set_cancel(context, True)
        await q.message.reply_text("Загрузка отменяется...")
    else:
        await q.message.reply_text("Нечего отменять.")