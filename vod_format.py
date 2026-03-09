import logging
import json
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


# ===== UI CONSTANTS =====
BTN_CHAT_HTML = "📖 Чат"
BTN_VOD_LINK = "🔗 Ссылка VOD"


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

    fmt = item.get("fmt")

    if fmt == "html_online":
        html_btn = InlineKeyboardButton(BTN_CHAT_HTML, url=html_url) if html_url else None
        vod_btn = InlineKeyboardButton(BTN_VOD_LINK, url=item.get("vod_url"))
        row = []
        if html_btn:
            row.append(html_btn)
        row.append(vod_btn)
        final_kb = InlineKeyboardMarkup([row])
    else:
        base_rows = list(kb.inline_keyboard) if kb else []
        if html_url:
            base_rows = base_rows + [[InlineKeyboardButton(BTN_CHAT_HTML, url=html_url)]]
        final_kb = InlineKeyboardMarkup(base_rows) if base_rows else None

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

    fmt = item.get("fmt")

    if fmt == "html_online":
        html_btn = InlineKeyboardButton(BTN_CHAT_HTML, url=html_url) if html_url else None
        vod_btn = InlineKeyboardButton(BTN_VOD_LINK, url=item.get("vod_url"))
        row = []
        if html_btn:
            row.append(html_btn)
        row.append(vod_btn)
        final_kb = InlineKeyboardMarkup([row])
    else:
        base_rows = list(kb.inline_keyboard) if kb else []
        if html_url:
            base_rows = base_rows + [[InlineKeyboardButton(BTN_CHAT_HTML, url=html_url)]]
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
        html_url = html_url if fmt == "html_online" else None

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
        html_url = public_html_url if fmt == "html_online" else None

        await _edit_progress_message_with_card(
            context=context,
            chat_id=chat_id,
            message_id=progress_message_id,
            item=item,
            html_url=html_url,
        )

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