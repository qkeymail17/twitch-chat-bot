from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import database as db
from ui import build_history_page, CB_UI_HISTORY, CB_HIST_PAGE, CB_HIST_FILES_PREFIX, CB_HIST_VOD_PREFIX


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


async def send_cached_files(context, chat_id: int, files: list[dict]):
    for f in files:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f["file_id"],
            filename=f.get("file_name"),
        )


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


async def history_files_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith(CB_HIST_FILES_PREFIX):
        return

    try:
        idx = int(data[len(CB_HIST_FILES_PREFIX):])
    except ValueError:
        return

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    if idx < 0 or idx >= len(items):
        await q.message.reply_text("Запрос не найден.")
        return

    vod_id = items[idx]["vod_id"]
    fmt = items[idx]["fmt"]
    cached = db.get_cache(vod_id, fmt)

    # HTML онлайн не имеет файлов — открываем ссылку
    if fmt == "html_online":
        html_url = cached.get("html_url") if cached else None
        if html_url:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="Открыть HTML:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Открыть HTML", url=html_url)]
                ]),
            )
        else:
            await q.message.reply_text("Ссылка не найдена.")
        return

    if not cached or not cached.get("files"):
        await q.message.reply_text("Файлы не найдены.")
        return

    await send_cached_files(context, q.message.chat_id, cached["files"])


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