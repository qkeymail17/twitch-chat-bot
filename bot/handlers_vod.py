# handlers_vod.py
import logging
import json
import re
from typing import Dict, List, Optional
from twitch_api import fetch_vod_meta, get_client_id

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
from modules.chat_downloader.download_worker import download_and_send
from ui import CB_FMT_HTML_ONLINE, build_format_keyboard
from handlers_state import (
    extract_vod_id_strict,
    is_busy,
    set_pending,
    set_busy,
    get_pending,
    clear_pending,
    pending_expired,
    set_cancel,
)
from ui_history import build_history_page
from ui_labels import CHAT_GENERIC, VOD_LINK, CANCEL
from ui_constants import CB_PENDING_CANCEL


def _make_item(meta, stats, vod_url, fmt):
    return {
        "channel": meta.get("channel"),
        "title": meta.get("title"),
        "created_at": meta.get("created_at"),
        "length_seconds": meta.get("length_seconds"),
        "messages": stats.get("messages"),
        "unique_users": stats.get("unique_users"),
        "vod_url": vod_url,
        "fmt": fmt,
    }


def _build_card(item):
    cards, _ = build_history_page([item], page=0, per_page=1)
    if not cards:
        return None, None
    return cards[0]


async def _edit_progress_message_with_card(context, chat_id: int, message_id: int, item: dict, html_url: str | None = None):
    text, kb = _build_card(item)
    if not text:
        return

    html_btn = InlineKeyboardButton(CHAT_GENERIC, url=html_url) if html_url else None
    vod_btn = InlineKeyboardButton(VOD_LINK, url=item.get("vod_url"))

    row = []
    if html_btn:
        row.append(html_btn)
    row.append(vod_btn)

    final_kb = InlineKeyboardMarkup([row])

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=final_kb,
        )
    except Exception:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=final_kb,
        )


async def _send_card_with_buttons(context, chat_id, item, html_url=None):
    text, kb = _build_card(item)
    if not text:
        return

    html_btn = InlineKeyboardButton(CHAT_GENERIC, url=html_url) if html_url else None
    vod_btn = InlineKeyboardButton(VOD_LINK, url=item.get("vod_url"))

    row = []
    if html_btn:
        row.append(html_btn)
    row.append(vod_btn)

    final_kb = InlineKeyboardMarkup([row])

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=final_kb,
    )


# ------ Entry handler (приём произвольного сообщения с VOD id) ------
async def vod_link_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = (update.message.text or "").strip()
    vod_id = extract_vod_id_strict(text)

    # fallback: ищем последнее длинное число в сообщении (7-12 цифр)
    if not vod_id:
        matches = re.findall(r"\d{7,12}", text)
        if matches:
            vod_id = matches[-1]

    if not vod_id:
        return

    if is_busy(context):
        await update.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    client_id = get_client_id()
    session = context.application.bot_data["aiohttp"]

    meta = await fetch_vod_meta(session, client_id, vod_id)

    # если VOD не существует — просто игнорируем сообщение
    if not meta or not getattr(meta, "length_seconds", None):
        return

    vod_url = f"https://www.twitch.tv/videos/{vod_id}"

    set_pending(context, vod_url=vod_url, vod_id=vod_id)

    await update.message.reply_text(
        "Выбери формат:",
        reply_markup=build_format_keyboard()
    )


# ------ Cancel pending download (кнопка отмены в прогрессе) ------
async def pending_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if is_busy(context):
        set_cancel(context, True)
    else:
        await q.message.reply_text("Нечего отменять.")


# ------ Cancel format selection (удалить pending) ------
async def format_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if get_pending(context):
        clear_pending(context)

    try:
        await q.message.delete()
    except Exception:
        pass


# ------ Format chosen handler (запуск воркера) ------
async def vod_format_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if is_busy(context):
        await q.message.reply_text("Я уже качаю чат. Подожди завершения.")
        return

    data = q.data or ""
    if data != CB_FMT_HTML_ONLINE:
        return

    pending = get_pending(context)
    if not pending:
        await q.message.reply_text("Ссылка не найдена.")
        return

    if pending_expired(pending):
        clear_pending(context)
        await q.message.reply_text("Ссылка устарела.")
        return

    fmt = "html_online"
    vod_url = pending["vod_url"]
    vod_id = pending["vod_id"]

    cached = db.get_cache(vod_id, fmt)
    if cached and not db.cache_is_expired(cached):
        clear_pending(context)
        db.add_user_history(update.effective_user.id, int(cached["id"]))

        meta_raw = cached.get("meta")
        stats_raw = cached.get("stats")
        html_url = cached.get("html_url")

        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        stats = json.loads(stats_raw) if isinstance(stats_raw, str) else (stats_raw or {})

        if not html_url:
            html_url = meta.get("html_url")

        safe_meta = {
            "channel": meta.get("channel") or "—",
            "title": meta.get("title") or "Без названия",
            "created_at": meta.get("created_at"),
            "length_seconds": meta.get("length_seconds") or 0,
        }

        safe_stats = {
            "messages": stats.get("messages") or 0,
            "unique_users": stats.get("unique_users") or 0,
        }

        item = _make_item(safe_meta, safe_stats, vod_url, fmt)

        try:
            await _edit_progress_message_with_card(
                context=context,
                chat_id=q.message.chat_id,
                message_id=q.message.message_id,
                item=item,
                html_url=html_url,
            )
        except Exception:
            await _send_card_with_buttons(context, q.message.chat_id, item, html_url)
        return

    clear_pending(context)
    set_busy(context, True)

    await q.message.edit_text(
        text="Загрузка...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(CANCEL, callback_data=CB_PENDING_CANCEL)]
        ])
    )

    progress_msg = q.message

    context.application.create_task(_runner(
        context=context,
        chat_id=q.message.chat_id,
        progress_message_id=progress_msg.message_id,
        vod_url=vod_url,
        vod_id=vod_id,
        fmt=fmt,
        user_id=update.effective_user.id,
    ))


async def _runner(context, chat_id: int, progress_message_id: int, vod_url: str, vod_id: str, fmt: str, user_id: int):
    try:
        meta, stats, files, public_html_url = await download_and_send(
            context=context,
            chat_id=chat_id,
            progress_message_id=progress_message_id,
            vod_url=vod_url,
            vod_id=vod_id,
            fmt=fmt,
        )

        if fmt == "html_online" and public_html_url:
            meta["html_url"] = public_html_url

        cache_id = db.upsert_cache(
            vod_id=vod_id,
            fmt=fmt,
            vod_url=vod_url,
            meta=meta,
            stats=stats,
            files=files,
        )
        db.add_user_history(user_id, cache_id)

        item = _make_item(meta, stats, vod_url, fmt)
        html_url = public_html_url

        await _edit_progress_message_with_card(
            context=context,
            chat_id=chat_id,
            message_id=progress_message_id,
            item=item,
            html_url=html_url,
        )

    except RuntimeError as e:
        if str(e) == "CHAT_EMPTY":
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message_id,
                    text="У этого VOD нет чата."
                )
            except Exception:
                pass
            return
        if "Загрузка была отменена." in str(e):
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message_id,
                    text="Загрузка была отменена.",
                )
            except Exception:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Загрузка была отменена.",
                )
            return
        raise

    except Exception as e:
        logging.exception("Download failed")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message_id,
                text=f"Ошибка: {type(e).__name__}: {e}",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Ошибка: {type(e).__name__}: {e}",
            )
    finally:
        set_busy(context, False)


__all__ = [
    "vod_link_entry",
    "vod_format_chosen",
    "pending_cancel_callback",
    "format_cancel_callback",
]