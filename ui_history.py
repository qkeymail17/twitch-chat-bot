import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *
from ui_formatters import _fmt_dt_utc, _fmt_len


def _format_button(it: dict, idx: int):
    fmt = it.get("fmt")

    # Онлайн HTML — кнопка не нужна (ссылка будет отдельной кнопкой ниже)
    if fmt == "html_online":
        return None

    if fmt == "html_local":
        return InlineKeyboardButton("📄 Чат HTML файл", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "txt":
        return InlineKeyboardButton("📝 Чат TXT файл", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "csv":
        return InlineKeyboardButton("📊 Чат CSV файл", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")

    return InlineKeyboardButton("📁 Файлы", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")


def _fmt_date_ru(dt: str) -> str:
    try:
        months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
        date_part, time_part, tz = dt.split(" ")
        y, m, d = date_part.split("-")
        m_txt = months[int(m) - 1]
        return f"{d} {m_txt} {y} {time_part} {tz}"
    except Exception:
        return dt


def build_history_page(items: list[dict], page: int, per_page: int):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    start = page * per_page
    end = min(start + per_page, total)
    page_items = items[start:end]

    cards = []

    for i, it in enumerate(page_items):
        idx = start + i

        channel = html.escape(it.get("channel") or "—")
        vod_title = html.escape(it.get("title") or "Без названия")
        dt_raw = _fmt_dt_utc(it.get("created_at"))
        dt = _fmt_date_ru(dt_raw)
        duration = _fmt_len(it.get("length_seconds"))
        msgs = it.get("messages") or 0
        users = it.get("unique_users") or 0

        text = (
            f"🟣 {channel}\n"
            f"🎬 {vod_title}\n"
            f"⏱ {duration} • 💬 {msgs} • 👥 {users}\n"
            f"🗓 {dt}"
        )

        buttons = []
        main_btn = _format_button(it, idx)
        if main_btn:
            buttons.append(main_btn)

        buttons.append(
            InlineKeyboardButton("🔗 Ссылка VOD", callback_data=f"{CB_HIST_VOD_PREFIX}{idx}")
        )

        kb = InlineKeyboardMarkup([buttons])
        cards.append((text, kb))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"{CB_HIST_PAGE}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=CB_NOOP))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"{CB_HIST_PAGE}{page + 1}"))

    nav_kb = InlineKeyboardMarkup([nav]) if nav else None

    return cards, nav_kb