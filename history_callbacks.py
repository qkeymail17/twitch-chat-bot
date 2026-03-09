from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def ui_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    user_id = update.effective_user.id

    # локальные импорты чтобы избежать циклических зависимостей
    import database as db
    from ui import CB_UI_HISTORY, CB_HIST_PAGE, CB_HIST_VOD_PREFIX, CB_HIST_FILES_PREFIX
    from history_view import _send_history_cards

    if data == CB_UI_HISTORY:
        items = db.get_history_for_user(user_id, limit=10, offset=0)
        await _send_history_cards(chat_id=q.message.chat_id, context=context, items=items, page=0)
        return

    if data.startswith(CB_HIST_VOD_PREFIX):
        return await history_vod_callback(update, context)

    if data.startswith(CB_HIST_FILES_PREFIX):
        return  # обрабатывается в history_files_callback

    if data.startswith(CB_HIST_PAGE):
        return await history_page_callback(update, context)


async def history_vod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    import database as db
    from ui import CB_HIST_VOD_PREFIX

    try:
        idx = int(data[len(CB_HIST_VOD_PREFIX):])
    except Exception:
        return

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    if idx < 0 or idx >= len(items):
        try:
            await q.message.reply_text("Запрос не найден.")
        except Exception:
            await context.bot.send_message(chat_id=q.message.chat_id, text="Запрос не найден.")
        return

    vod_url = items[idx].get("vod_url")
    if not vod_url:
        try:
            await q.message.reply_text("Ссылка не найдена.")
        except Exception:
            await context.bot.send_message(chat_id=q.message.chat_id, text="Ссылка не найдена.")
        return

    try:
        await q.message.reply_text(f"<code>{vod_url}</code>", parse_mode="HTML")
    except Exception:
        await context.bot.send_message(chat_id=q.message.chat_id, text=vod_url)


async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    from ui import CB_HIST_PAGE
    try:
        page = int(data[len(CB_HIST_PAGE):])
    except Exception:
        return

    import database as db
    # build_history_page может быть в ui — импорт локально
    from ui import build_history_page

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    cards, nav_kb = build_history_page(items, page=page, per_page=1)

    if not cards:
        try:
            await q.message.edit_text("История пуста.")
        except Exception:
            await context.bot.send_message(chat_id=q.message.chat_id, text="История пуста.")
        return

    text, card_kb = cards[0]

    # объединение клавиатур — аккуратно: обе могут быть InlineKeyboardMarkup или None
    if card_kb is not None and nav_kb is not None:
        combined_kb = InlineKeyboardMarkup(list(card_kb.inline_keyboard) + list(nav_kb.inline_keyboard))
    elif card_kb is not None:
        combined_kb = card_kb
    else:
        combined_kb = nav_kb

    try:
        await q.message.edit_text(text, parse_mode="HTML", reply_markup=combined_kb)
    except Exception:
        await context.bot.send_message(chat_id=q.message.chat_id, text=text, parse_mode="HTML", reply_markup=combined_kb)