from telegram import Update
from telegram.ext import ContextTypes


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()