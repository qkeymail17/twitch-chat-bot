from telegram import Update
from telegram.ext import ContextTypes

from handlers_state import get_pending, clear_pending


async def format_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if get_pending(context):
        clear_pending(context)

    try:
        await q.message.delete()
    except Exception:
        pass