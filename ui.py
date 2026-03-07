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
CB_NOOP = "noop"


# =========================
# Keyboards
# =========================
def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("HTML ссылка", callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton("HTML файл", callback_data=CB_FMT_HTML_LOCAL),
        ],
        [
            InlineKeyboardButton("TXT", callback_data=CB_FMT_TXT),
            InlineKeyboardButton("CSV", callback_data=CB_FMT_CSV),
        ],
        [
            InlineKeyboardButton("Отмена", callback_data=CB_PENDING_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([])


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


def human_dt(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


# =========================
# History (будет переработана дальше)
# =========================
def build_history_page(items: list[dict], page: int, per_page: int):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    lines = ["История:\n"]
    keyboard = []

    for i, it in enumerate(page_items, start=1):
        vod_url = it.get("vod_url", "—")
        title = html.escape(it.get("title") or "—")

        keyboard.append([
            InlineKeyboardButton(f"Файлы {i}", callback_data=f"{CB_HIST_FILES_PREFIX}{start + (i - 1)}"),
            InlineKeyboardButton("Открыть", url=vod_url),
        ])

        lines.append(
            f"{i})\n"
            f"<code>{vod_url}</code>\n"
            f"{title}"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("←", callback_data=f"{CB_HIST_PAGE}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=CB_NOOP))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("→", callback_data=f"{CB_HIST_PAGE}{page + 1}"))

    keyboard.append(nav)
    return "\n\n".join(lines), InlineKeyboardMarkup(keyboard)