import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
from download_worker import download_and_send
from ui import (
    build_format_keyboard,
    CB_FMT_TXT, CB_FMT_CSV,
    CB_FMT_HTML_ONLINE, CB_FMT_HTML_LOCAL,
)
from handlers_state import (
    extract_vod_id_strict, is_busy, set_busy,
    set_pending, get_pending, clear_pending, pending_expired,
)
from handlers_history import send_cached_files


async def vod_link_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (update.message.text or "").strip()
    vod_id = extract_vod_id_strict(text)
    if not vod_id:
        return

    if is_busy(context):
        await update.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    set_pending(context, vod_url=text, vod_id=vod_id)
    await update.message.reply_text("Выбери формат:", reply_markup=build_format_keyboard())


async def vod_format_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if is_busy(context):
        await q.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    data = q.data or ""
    if data not in (CB_FMT_TXT, CB_FMT_CSV, CB_FMT_HTML_ONLINE, CB_FMT_HTML_LOCAL):
        return

    pending = get_pending(context)
    if not pending:
        await q.message.reply_text("Ссылка не найдена.")
        return

    if pending_expired(pending):
        clear_pending(context)
        await q.message.reply_text("Ссылка устарела.")
        return

    FMT_MAP = {
        CB_FMT_TXT: "txt",
        CB_FMT_CSV: "csv",
        CB_FMT_HTML_ONLINE: "html_online",
        CB_FMT_HTML_LOCAL: "html_local",
    }

    fmt = FMT_MAP[data]
    vod_url = pending["vod_url"]
    vod_id = pending["vod_id"]

    cached = db.get_cache(vod_id, fmt)
    if cached and not db.cache_is_expired(cached) and (
            cached.get("files") or (fmt == "html_online" and cached.get("html_url"))):
        clear_pending(context)

        # отправляем файлы из кэша (если есть) и добавляем в историю
        if cached.get("files"):
            await send_cached_files(context, q.message.chat_id, cached["files"])
        db.add_user_history(update.effective_user.id, int(cached["id"]))

        # для html_online — показываем ссылку
        if fmt == "html_online":
            html_url = cached.get("html_url")
            if html_url:
                vod = cached.get("vod_url")
                text = f"<code>{vod}</code>"
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌐 Открыть HTML", url=html_url)]
                    ]),
                )
        return

    clear_pending(context)
    set_busy(context, True)

    progress_msg = await context.bot.send_message(chat_id=q.message.chat_id, text="Старт…")

    async def runner():
        try:
            meta, stats, files, public_html_url = await download_and_send(
                context=context,
                chat_id=q.message.chat_id,
                progress_message_id=progress_msg.message_id,
                vod_url=vod_url,
                vod_id=vod_id,
                fmt=fmt,
            )

            # сохраняем в кэш и историю (как было в оригинале)
            cache_id = db.upsert_cache(
                vod_id=vod_id,
                fmt=fmt,
                vod_url=vod_url,
                meta=meta,
                stats=stats,
                files=files,
            )
            db.add_user_history(update.effective_user.id, cache_id)

            # если это html_online и public_html_url вернулся — показываем ссылку
            if fmt == "html_online" and public_html_url:
                text = f"<code>{vod_url}</code>"
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌐 Открыть HTML", url=public_html_url)]
                    ]),
                )

        except Exception as e:
            logging.exception("Download failed")
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=f"Ошибка: {type(e).__name__}: {e}",
            )
        finally:
            set_busy(context, False)

    context.application.create_task(runner())


async def pending_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if get_pending(context):
        clear_pending(context)
        await q.message.reply_text("Ок, отменил.")
    else:
        await q.message.reply_text("Нечего отменять.")