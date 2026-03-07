# handlers.py
import time
import logging
from typing import Optional
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import VOD_URL_RE, PENDING_TTL_SECONDS
from ui import (
    build_format_keyboard,
    build_about_keyboard,
    about_text,
    build_history_page,
    CB_FMT_TXT, CB_FMT_CSV,
    CB_FMT_HTML_ONLINE, CB_FMT_HTML_LOCAL,
    CB_PENDING_CANCEL,
    CB_UI_HISTORY,
    CB_HIST_PAGE, CB_HIST_FILES_PREFIX, CB_HIST_VOD_PREFIX,
)
import database as db
from download_worker import download_and_send


# ===== HISTORY HELPERS =====
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


def extract_vod_id_strict(url: str) -> Optional[str]:
    m = VOD_URL_RE.match(url.strip())
    return m.group(1) if m else None


def is_busy(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("vod_busy"))


def set_busy(context: ContextTypes.DEFAULT_TYPE, v: bool):
    context.user_data["vod_busy"] = v


def set_pending(context: ContextTypes.DEFAULT_TYPE, vod_url: str, vod_id: str):
    context.user_data["vod_pending"] = {
        "vod_url": vod_url,
        "vod_id": vod_id,
        "created_at": time.time(),
    }


def get_pending(context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    return context.user_data.get("vod_pending")


def clear_pending(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("vod_pending", None)


def pending_expired(p: dict) -> bool:
    return (time.time() - float(p.get("created_at") or 0)) > PENDING_TTL_SECONDS


def _fmt_dt_utc(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text(
        "Просто отправь ссылку на Twitch VOD:\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>",
        parse_mode="HTML",
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text(
        about_text(),
        parse_mode="HTML",
        reply_markup=build_about_keyboard(),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if is_busy(context):
        await msg.reply_text("Сейчас идёт скачивание.")
        return

    if get_pending(context):
        clear_pending(context)
        await msg.reply_text("Ок, отменил.")
    else:
        await msg.reply_text("Нечего отменять.")


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

        await send_cached_files(context, q.message.chat_id, cached["files"])
        db.add_user_history(update.effective_user.id, int(cached["id"]))

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

            cache_id = db.upsert_cache(
                vod_id=vod_id,
                fmt=fmt,
                vod_url=vod_url,
                meta=meta,
                stats=stats,
                files=files,
            )
            db.add_user_history(update.effective_user.id, cache_id)

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


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()