import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

import database as db
from download_worker import download_and_send
from ui import CB_FMT_TXT, CB_FMT_CSV, CB_FMT_HTML_ONLINE, CB_FMT_HTML_LOCAL
from handlers_state import (
    is_busy, set_busy, get_pending, clear_pending, pending_expired,
)
from handlers_history import send_cached_files
from ui_history import build_history_page


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
    """
    Edit existing message (progress message) to final card + keyboard.
    Ensures safe merging of keyboard rows (handles tuple/list).
    Special-case: for html_online produce a single row with two URL buttons:
        [🌐 Открыть HTML] [🔗 Ссылка VOD]
    For other formats — keep keyboard produced by ui_history, and if html_url is present,
    append an extra row with Open HTML button.
    """
    text, kb = _build_card(item)
    if not text:
        return

    fmt = item.get("fmt")

    # Build final keyboard depending on type
    if fmt == "html_online":
        # single row with two url buttons
        html_btn = InlineKeyboardButton("🌐 Чат HTML ссылка", url=html_url) if html_url else None
        vod_btn = InlineKeyboardButton("🔗 Ссылка VOD", url=item.get("vod_url"))
        row = []
        if html_btn:
            row.append(html_btn)
        row.append(vod_btn)
        final_kb = InlineKeyboardMarkup([row])
    else:
        # For other formats: take keyboard from ui_history and ensure it's a list of rows.
        base_rows = list(kb.inline_keyboard) if kb else []
        # If there is an html_url (rare for non-online), attach as extra row
        if html_url:
            base_rows = base_rows + [[InlineKeyboardButton("🌐 Чат HTML ссылка", url=html_url)]]
        final_kb = InlineKeyboardMarkup(base_rows) if base_rows else None

    # edit message text + reply_markup
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=final_kb,
        )
    except Exception:
        # fallback: if edit fails (message deleted, etc.) — send a fresh message
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=final_kb,
        )


async def _send_card_with_buttons(context, chat_id, item, html_url=None):
    """
    Backward-compatible helper: send a new message (used only if we cannot edit a progress message).
    Kept for safety; tries to produce the same keyboard layout as _edit_progress_message_with_card.
    """
    text, kb = _build_card(item)
    if not text:
        return

    fmt = item.get("fmt")

    if fmt == "html_online":
        html_btn = InlineKeyboardButton("🌐 Чат HTML ссылка", url=html_url) if html_url else None
        vod_btn = InlineKeyboardButton("🔗 Ссылка VOD", url=item.get("vod_url"))
        row = []
        if html_btn:
            row.append(html_btn)
        row.append(vod_btn)
        final_kb = InlineKeyboardMarkup([row])
    else:
        base_rows = list(kb.inline_keyboard) if kb else []
        if html_url:
            base_rows = base_rows + [[InlineKeyboardButton("🌐 Открыть HTML", url=html_url)]]
        final_kb = InlineKeyboardMarkup(base_rows) if base_rows else None

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=final_kb,
    )


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
    if cached and not db.cache_is_expired(cached):
        # we will not auto-send files on cached path — user will request via "Файлы" button
        clear_pending(context)

        db.add_user_history(update.effective_user.id, int(cached["id"]))

        meta = cached.get("meta") or {}
        stats = cached.get("stats") or {}

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
        html_url = cached.get("html_url") if fmt == "html_online" else None

        # Try to edit original callback message (so no new messages appear)
        try:
            await _edit_progress_message_with_card(
                context=context,
                chat_id=q.message.chat_id,
                message_id=q.message.message_id,
                item=item,
                html_url=html_url,
            )
        except Exception:
            # fallback: send as new message
            await _send_card_with_buttons(context, q.message.chat_id, item, html_url)
        return

    clear_pending(context)
    set_busy(context, True)

    progress_msg = await context.bot.send_message(chat_id=q.message.chat_id, text="Загрузка...")

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
        html_url = public_html_url if fmt == "html_online" else None

        # Edit the original progress message (no new message)
        await _edit_progress_message_with_card(
            context=context,
            chat_id=chat_id,
            message_id=progress_message_id,
            item=item,
            html_url=html_url,
        )

    except Exception as e:
        logging.exception("Download failed")
        # edit progress message to show error if possible, else send new message
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