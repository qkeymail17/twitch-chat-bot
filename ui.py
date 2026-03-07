import html
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# =========================
# Callback constants
# =========================
CB_FMT_TXT = "vodfmt:txt"
CB_FMT_CSV = "vodfmt:csv"
CB_FMT_HTML_ONLINE = "vodfmt:html_online"
CB_FMT_HTML_LOCAL = "vodfmt:html_offline"
CB_PENDING_CANCEL = "vod:pending_cancel"

CB_UI_HISTORY = "ui:history"

CB_HIST_PAGE = "ui:histpage:"
CB_HIST_FILES_PREFIX = "ui:histfiles:"
CB_HIST_VOD_PREFIX = "ui:histvod:"
CB_NOOP = "noop"


# =========================
# Keyboards
# =========================
def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 HTML ссылка", callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton("📄 HTML файл", callback_data=CB_FMT_HTML_LOCAL),
        ],
        [
            InlineKeyboardButton("📝 TXT", callback_data=CB_FMT_TXT),
            InlineKeyboardButton("📊 CSV", callback_data=CB_FMT_CSV),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data=CB_PENDING_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 История", callback_data=CB_UI_HISTORY)]
    ])


# =========================
# Progress text
# =========================
def build_progress_text(meta: dict, vod_url: str, fmt: str, messages: int, unique_users: int, parts: int, elapsed_s: float, done: bool) -> str:
    title = meta.get("title") or "—"
    channel = meta.get("channel") or "—"
    vod_len = meta.get("vod_len") or "—"
    elapsed = fmt_hhmmss(int(elapsed_s))
    status_line = "Готово" if done else "Качаю…"

    return (
        f"{status_line}\n\n"
        f"VOD: <code>{vod_url}</code>\n"
        f"Канал: <b>{html.escape(channel)}</b>\n"
        f"Название: <b>{html.escape(title)}</b>\n"
        f"Длина VOD: <b>{vod_len}</b>\n"
        f"Формат: <b>{fmt.upper()}</b>\n\n"
        f"Сообщений: <b>{messages}</b>\n"
        f"Уникальных юзеров: <b>{unique_users}</b>\n"
        f"Файл: <b>{parts}</b>\n"
        f"Прошло времени: <b>{elapsed}</b>"
    )


def fmt_hhmmss(total_seconds: int) -> str:
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# =========================
# Text blocks
# =========================
def about_text() -> str:
    return (
        "Что умеет бот:\n"
        "— Скачивает чат открытого Twitch VOD в TXT / CSV / HTML\n\n"
        "Как пользоваться:\n"
        "1) Просто отправь ссылку на VOD:\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>\n"
        "2) Выбери формат кнопкой"
    )


# =========================
# History — новый дизайн
# =========================
def _fmt_dt_utc(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"


def _fmt_len(seconds: int | None) -> str:
    if not seconds:
        return "—"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_button(fmt: str, idx: int) -> InlineKeyboardButton:
    if fmt == "html_online":
        return InlineKeyboardButton("🌐 Открыть HTML", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "html_local":
        return InlineKeyboardButton("📄 Скачать HTML", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "txt":
        return InlineKeyboardButton("📝 Скачать TXT", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "csv":
        return InlineKeyboardButton("📊 Скачать CSV", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    return InlineKeyboardButton("📁 Файлы", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")


def build_history_page(items: list[dict], page: int, per_page: int):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    blocks = []
    keyboard = []

    for i, it in enumerate(page_items):
        idx = start + i

        channel = html.escape(it.get("channel") or "—")
        dt = _fmt_dt_utc(it.get("created_at"))
        duration = _fmt_len(it.get("length_seconds"))
        msgs = it.get("messages") or 0
        users = it.get("unique_users") or 0
        fmt = it.get("fmt")

        block = (
            f"Канал: {channel}\n"
            f"Дата: {dt}\n"
            f"Длительность: {duration}\n"
            f"Сообщений: {msgs}\n"
            f"Пользователей: {users}"
        )
        blocks.append(block)

        keyboard.append([
            _format_button(fmt, idx),
            InlineKeyboardButton("🔗 Показать ссылку VOD", callback_data=f"{CB_HIST_VOD_PREFIX}{idx}")
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"{CB_HIST_PAGE}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=CB_NOOP))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"{CB_HIST_PAGE}{page + 1}"))

    keyboard.append(nav)

    return "\n\n".join(blocks), InlineKeyboardMarkup(keyboard)