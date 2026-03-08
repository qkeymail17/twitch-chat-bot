from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import database as db


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