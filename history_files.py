from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import database as db
from ui_history import build_history_page


async def send_cached_files(context, chat_id: int, files: list[dict]):
    for f in files:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f["file_id"],
            filename=f.get("file_name"),
        )


async def history_files_callback(update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith("ui:histfiles:"):
        return

    try:
        idx = int(data[len("ui:histfiles:"):])
    except ValueError:
        return

    items = db.get_history_for_user(update.effective_user.id, limit=10, offset=0)
    if idx < 0 or idx >= len(items):
        await q.message.reply_text("Запрос не найден.")
        return

    vod_id = items[idx]["vod_id"]
    fmt = items[idx]["fmt"]
    cached = db.get_cache(vod_id, fmt)

    # Готовим данные карточки
    meta = (cached.get("meta") if cached else None) or {}
    stats = (cached.get("stats") if cached else None) or {}
    vod_url = (cached.get("vod_url") if cached else None) or items[idx].get("vod_url")

    item = {
        "channel": meta.get("channel"),
        "title": meta.get("title"),
        "created_at": meta.get("created_at"),
        "length_seconds": meta.get("length_seconds"),
        "messages": stats.get("messages"),
        "unique_users": stats.get("unique_users"),
        "vod_url": vod_url,
        "fmt": fmt,
        "html_url": (cached.get("html_url") if cached else None),
    }

    # HTML online — вместо "Открыть HTML:" показываем карточку с кнопкой
    if fmt == "html_online":
        html_url = item.get("html_url")
        if not html_url:
            await q.message.reply_text("Ссылка не найдена.")
            return

        cards, _ = build_history_page([item], page=0, per_page=1)
        text, kb = cards[0]

        extra_rows = [[InlineKeyboardButton("🌐 Чат HTML ссылка", url=html_url)]]
        merged = (kb.inline_keyboard if kb else []) + extra_rows
        kb_final = InlineKeyboardMarkup(merged)

        await context.bot.send_message(
            chat_id=q.message.chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb_final,
        )
        return

    # Остальные форматы — нужны файлы
    if not cached or not cached.get("files"):
        await q.message.reply_text("Файлы не найдены.")
        return

    # Сначала отправляем файлы
    await send_cached_files(context, q.message.chat_id, cached["files"])

    # Потом карточку
    cards, _ = build_history_page([item], page=0, per_page=1)
    text, kb = cards[0]

    html_url = item.get("html_url")
    extra_rows = []
    if html_url:
        extra_rows.append([InlineKeyboardButton("🌐 Открыть HTML", url=html_url)])

    merged = (kb.inline_keyboard if kb else []) + extra_rows
    kb_final = InlineKeyboardMarkup(merged) if merged else None

    await context.bot.send_message(
        chat_id=q.message.chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb_final,
    )