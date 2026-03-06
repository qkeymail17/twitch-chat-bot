import time
import logging
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import VOD_URL_RE, PENDING_TTL_SECONDS
from ui import (
    build_format_keyboard,
    build_info_keyboard,
    build_about_keyboard,
    build_timezone_keyboard,
    about_text,
    build_history_page,
    tz_label,
    CB_FMT_TXT, CB_FMT_CSV,
    CB_FMT_HTML_ONLINE, CB_FMT_HTML_LOCAL,
    CB_PENDING_CANCEL,
    CB_UI_HISTORY,
    CB_HIST_PAGE, CB_HIST_FILES_PREFIX,
    CB_TZ_OPEN, CB_TZ_DEC_H, CB_TZ_INC_H, CB_TZ_SAVE, CB_TZ_CANCEL,
)
import database as db
from download_worker import download_and_send


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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    await msg.reply_text(
        "Просто отправь ссылку на Twitch VOD:\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>",
        parse_mode="HTML",
        reply_markup=build_info_keyboard(),
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user_id = update.effective_user.id
    tz_offset_min = db.get_user_tz_offset(user_id)
    tz = tz_label(tz_offset_min)

    await msg.reply_text(
        about_text(tz),
        parse_mode="HTML",
        reply_markup=build_about_keyboard(),
    )


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user_id = update.effective_user.id
    tz_offset_min = db.get_user_tz_offset(user_id)

    context.user_data["tz_draft"] = tz_offset_min

    await msg.reply_text(
        f"Часовой пояс: <b>{tz_label(tz_offset_min)}</b>",
        parse_mode="HTML",
        reply_markup=build_timezone_keyboard(tz_offset_min),
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if is_busy(context):
        await msg.reply_text("Сейчас идёт скачивание. /cancel отменяет только ожидание выбора формата.")
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
        await update.message.reply_text("Я уже качаю чат. Подожди завершения и отправь ссылку снова.")
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
        await q.message.reply_text("Ссылка не найдена. Просто отправь ссылку на VOD ещё раз.")
        return

    if pending_expired(pending):
        clear_pending(context)
        await q.message.reply_text("Ссылка устарела. Отправь VOD-ссылку ещё раз.")
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

    # --- DB cache hit ---
    cached = db.get_cache(vod_id, fmt)
    if cached and not db.cache_is_expired(cached) and cached.get("files"):
        clear_pending(context)
        await q.message.reply_text("Нашёл в кэше. Отправляю без повторного скачивания…")

        await send_cached_files(context, q.message.chat_id, cached["files"])

        db.add_user_history(update.effective_user.id, int(cached["id"]))
        # если HTML online — заново публикуем html и даём ссылку
        if fmt == "html_online":
            from html_renderer import render_viewer_html
            from html_publisher import publish_html

            meta = cached.get("meta") or {}
            stats = cached.get("stats") or {}

            # HTML заново не пересобираем, просто публикуем заглушку
            # (можно улучшить потом, но ссылка будет работать)
            public_html_url = publish_html("<html><body><h2>HTML уже создан ранее</h2></body></html>")

            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="Открыть HTML в браузере:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("HTML online", url=public_html_url)]
                ]),
            )
        await q.message.reply_text("Готово.", reply_markup=build_info_keyboard())
        return

    # --- download ---
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

            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="Готово.",
                reply_markup=build_info_keyboard(),
            )

            if fmt == "html_online" and public_html_url:
                await context.bot.send_message(
                    chat_id=q.message.chat_id,
                    text="Открыть HTML в браузере:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("HTML online", url=public_html_url)]
                    ]),
                )

        except Exception as e:
            logging.exception(
                "Download failed (vod_id=%s fmt=%s user_id=%s)",
                vod_id, fmt, update.effective_user.id
            )
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


def _clamp_tz_offset_min(offset_min: int) -> int:
    return max(-12 * 60, min(14 * 60, int(offset_min)))


async def timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    user_id = update.effective_user.id

    def _get_draft() -> int:
        v = context.user_data.get("tz_draft")
        if v is None:
            return db.get_user_tz_offset(user_id)
        try:
            return int(v)
        except Exception:
            return db.get_user_tz_offset(user_id)

    async def _edit_or_reply(text: str, kb):
        if q and q.message:
            try:
                await q.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
                return
            except Exception:
                pass
        if q and q.message:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    if data == CB_TZ_OPEN:
        draft = db.get_user_tz_offset(user_id)
        draft = _clamp_tz_offset_min(draft)
        context.user_data["tz_draft"] = draft
        await _edit_or_reply(
            f"Часовой пояс: <b>{tz_label(draft)}</b>",
            build_timezone_keyboard(draft),
        )
        return

    if data == CB_TZ_DEC_H:
        draft = _clamp_tz_offset_min(_get_draft() - 60)
        context.user_data["tz_draft"] = draft
        await _edit_or_reply(
            f"Часовой пояс: <b>{tz_label(draft)}</b>",
            build_timezone_keyboard(draft),
        )
        return

    if data == CB_TZ_INC_H:
        draft = _clamp_tz_offset_min(_get_draft() + 60)
        context.user_data["tz_draft"] = draft
        await _edit_or_reply(
            f"Часовой пояс: <b>{tz_label(draft)}</b>",
            build_timezone_keyboard(draft),
        )
        return

    if data == CB_TZ_SAVE:
        draft = _clamp_tz_offset_min(_get_draft())
        db.set_user_tz_offset(user_id, draft)
        context.user_data.pop("tz_draft", None)

        tz = tz_label(draft)
        await _edit_or_reply(
            f"Часовой пояс сохранён: <b>{tz}</b>",
            build_about_keyboard(),
        )
        return

    if data == CB_TZ_CANCEL:
        context.user_data.pop("tz_draft", None)
        tz_offset_min = db.get_user_tz_offset(user_id)
        tz = tz_label(tz_offset_min)
        await _edit_or_reply(about_text(tz), build_about_keyboard())
        return


async def ui_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    user_id = update.effective_user.id

    if data == CB_UI_HISTORY:
        items = db.get_history_for_user(user_id, limit=20, offset=0)
        if not items:
            await q.message.reply_text("История пуста.")
            return

        tz_offset_min = db.get_user_tz_offset(user_id)
        text, kb = build_history_page(items, page=0, per_page=5, tz_offset_min=tz_offset_min)
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
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

    items = db.get_history_for_user(update.effective_user.id, limit=20, offset=0)
    if not items:
        await q.message.reply_text("История пуста.")
        return

    tz_offset_min = db.get_user_tz_offset(update.effective_user.id)
    text, kb = build_history_page(items, page=page, per_page=5, tz_offset_min=tz_offset_min)
    await q.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


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

    items = db.get_history_for_user(update.effective_user.id, limit=20, offset=0)
    if idx < 0 or idx >= len(items):
        await q.message.reply_text("Запрос не найден.")
        return

    vod_id = items[idx]["vod_id"]
    fmt = items[idx]["fmt"]
    cached = db.get_cache(vod_id, fmt)
    if not cached or not cached.get("files"):
        await q.message.reply_text("Файлы не найдены.")
        return

    await q.message.reply_text("Отправляю файлы…")
    await send_cached_files(context, q.message.chat_id, cached["files"])


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()