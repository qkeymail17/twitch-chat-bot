from telegram.ext import ContextTypes
from ui import build_history_page


async def _send_history_cards(chat_id: int, context: ContextTypes.DEFAULT_TYPE, items: list, page: int):
    cards, nav_kb = build_history_page(items, page=page, per_page=2)

    for text, kb in cards:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb,
        )

    if nav_kb:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Навигация:",
            reply_markup=nav_kb,
        )