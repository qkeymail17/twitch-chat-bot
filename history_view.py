from telegram.ext import ContextTypes
from ui_history import build_history_message


async def send_history_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, items: list, page: int):
    text, kb = build_history_message(items, page=page)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb,
    )