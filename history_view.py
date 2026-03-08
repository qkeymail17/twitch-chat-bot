from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes
from ui import build_history_page


async def _send_history_cards(chat_id: int, context: ContextTypes.DEFAULT_TYPE, items: list, page: int):
    """Send a single history card (one stream per page) with combined action + navigation buttons.

    This replaces the previous behaviour of sending multiple messages (one per card)
    and a separate 'navigation' message. Now one message contains card buttons and
    navigation row, so it can be edited in-place when user switches pages.
    """

    # build page with a single item per page
    cards, nav_kb = build_history_page(items, page=page, per_page=1)

    if not cards:
        await context.bot.send_message(chat_id=chat_id, text="История пуста.")
        return

    # take the first (and only) card for this page
    text, card_kb = cards[0]

    # merge card keyboard and navigation keyboard into a single InlineKeyboardMarkup
    combined_kb = None
    if card_kb and nav_kb:
        combined_kb = InlineKeyboardMarkup(card_kb.inline_keyboard + nav_kb.inline_keyboard)
    elif card_kb:
        combined_kb = card_kb
    else:
        combined_kb = nav_kb

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=combined_kb,
    )