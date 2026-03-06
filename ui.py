import html
import time
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import PENDING_TTL_SECONDS


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

CB_TZ_OPEN = "ui:tz"
CB_TZ_DEC_H = "ui:tzdec"
CB_TZ_INC_H = "ui:tzinc"
CB_TZ_SAVE = "ui:tzsave"
CB_TZ_CANCEL = "ui:tzcancel"


# =========================
# Timezone helpers
# =========================
def tz_label(offset_min: int) -> str:
    sign = "+" if offset_min >= 0 else "-"
    total_min = abs(offset_min)
    h = total_min // 60
    m = total_min % 60
    if m == 0:
        return f"UTC{sign}{h}"
    return f"UTC{sign}{h}:{m:02d}"


def fmt_stream_time(iso: str | None, offset_min: int) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        tz = timezone(timedelta(minutes=offset_min))
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


# =========================
# Keyboards
# =========================
def build_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("TXT", callback_data=CB_FMT_TXT),
            InlineKeyboardButton("CSV", callback_data=CB_FMT_CSV),
        ],
        [
            InlineKeyboardButton("HTML (онлайн)", callback_data=CB_FMT_HTML_ONLINE),
            InlineKeyboardButton("HTML offline", callback_data=CB_FMT_HTML_LOCAL),
        ],
        [
            InlineKeyboardButton("Отмена", callback_data=CB_PENDING_CANCEL),
        ]
    ])


def build_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("История", callback_data=CB_UI_HISTORY)],
    ])


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Часовой пояс", callback_data=CB_TZ_OPEN)],
        [InlineKeyboardButton("История", callback_data=CB_UI_HISTORY)],
    ])


def build_timezone_keyboard(draft_offset_min: int) -> InlineKeyboardMarkup:
    draft_offset_min = max(-12 * 60, min(14 * 60, int(draft_offset_min)))

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("−1ч", callback_data=CB_TZ_DEC_H),
            InlineKeyboardButton("+1ч", callback_data=CB_TZ_INC_H),
        ],
        [
            InlineKeyboardButton("Сохранить", callback_data=CB_TZ_SAVE),
            InlineKeyboardButton("Отмена", callback_data=CB_TZ_CANCEL),
        ],
    ])


# =========================
# Progress text
# =========================
def build_progress_text(meta: dict, vod_url: str, fmt: str, messages: int, unique_users: int, parts: int, elapsed_s: float, done: bool) -> str:
    title = meta.get("title") or "—"
    channel = meta.get("channel") or "—"
    vod_len = meta.get("vod_len") or "—"
    elapsed = fmt_hhmmss(int(elapsed_s))
    status_line = "Готово ✅" if done else "Качаю…"

    return (
        f"{status_line}\n\n"
        f"VOD: <code>{vod_url}</code>\n"
        f"Канал: <b>{html.escape(channel)}</b>\n"
        f"Название: <b>{html.escape(title)}</b>\n"
        f"Длина VOD: <b>{vod_len}</b>\n"
        f"Формат: <b>{fmt.upper()}</b>\n\n"
        f"Сообщений: <b>{messages}</b>\n"
        f"Уникальных юзеров: <b>{unique_users}</b>\n"
        f"Файлов-частей: <b>{parts}</b>\n"
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
def about_text(current_tz_label: str) -> str:
    return (
        "Что умеет бот:\n"
        "— Скачивает чат открытого Twitch VOD в TXT / CSV / HTML\n\n"
        "Как пользоваться:\n"
        "1) Просто отправь ссылку на VOD:\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>\n"
        "2) Выбери формат кнопкой\n\n"
        f"Текущий часовой пояс: <b>{current_tz_label}</b>"
    )


def human_dt(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


# =========================
# History
# =========================
def build_history_page(items: list[dict], page: int, per_page: int, tz_offset_min: int):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    header = f"История (YYYY-MM-DD HH:MM) [{tz_label(tz_offset_min)}]\n"
    lines = [header]
    keyboard = []

    for i, it in enumerate(page_items, start=1):
        ts = fmt_stream_time(it.get("created_at"), tz_offset_min)
        vod_url = it.get("vod_url", "—")
        title = html.escape(it.get("title") or "—")

        keyboard.append([
            InlineKeyboardButton(f"Файлы {i}", callback_data=f"{CB_HIST_FILES_PREFIX}{start + (i - 1)}"),
            InlineKeyboardButton("Открыть", url=vod_url),
        ])

        lines.append(
            f"{i}) <b>{ts}</b>\n"
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