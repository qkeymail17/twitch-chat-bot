from telegram import Update
from telegram.ext import ContextTypes

from handlers_state import get_pending, clear_pending


async def pending_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if get_pending(context):
        clear_pending(context)
        await q.message.reply_text("Ок, отменил.")
    else:
        await q.message.reply_text("Нечего отменять.")