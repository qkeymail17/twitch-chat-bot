import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *
from ui_formatters import _fmt_dt_utc, _fmt_len
from ui_labels import CHAT_GENERIC, FILES, VOD_LINK, label_for_fmt


def _format_button(it: dict, idx: int):
    fmt = it.get("fmt")

    if fmt == "html_online":
        url = it.get("html_url")
        if url:
            return InlineKeyboardButton(CHAT_GENERIC, url=url)

    if fmt == "html_local":
        cache_id = it.get("id")
        return InlineKeyboardButton(CHAT_GENERIC, callback_data=f"{CB_HIST_FILES_PREFIX}{cache_id}")
    if fmt == "txt":
        cache_id = it.get("id")
        return InlineKeyboardButton(CHAT_GENERIC, callback_data=f"{CB_HIST_FILES_PREFIX}{cache_id}")
    if fmt == "csv":
        cache_id = it.get("id")
        return InlineKeyboardButton(CHAT_GENERIC, callback_data=f"{CB_HIST_FILES_PREFIX}{cache_id}")

    cache_id = it.get("id")
    return InlineKeyboardButton(FILES, callback_data=f"{CB_HIST_FILES_PREFIX}{cache_id}")


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

        created_at = it.get("created_at")
        dt_raw = _fmt_dt_utc(created_at) if created_at else "—"
        dt = _fmt_date_ru(dt_raw) if dt_raw != "—" else "—"

        length_seconds = it.get("length_seconds")
        duration = _fmt_len(length_seconds) if length_seconds else "—"

        msgs = it.get("messages") or 0
        users = it.get("unique_users") or 0
        fmt = it.get("fmt") or "—"

        fmt_text = label_for_fmt(fmt)

        text = (
            f"🟣 {channel}\n"
            f"🎬 {vod_title}\n"
            f"⏱ {duration} • 💬 {msgs} • 👥 {users}\n"
            f"🗓 {dt}\n"
            f"{fmt_text}"
        )

        buttons = []
        main_btn = _format_button(it, idx)
        if main_btn:
            buttons.append(main_btn)

        vod_url = it.get("vod_url")
        if vod_url:
            buttons.append(
                InlineKeyboardButton(VOD_LINK, url=vod_url)
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