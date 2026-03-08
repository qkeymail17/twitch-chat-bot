import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ui_constants import *
from ui_formatters import _fmt_dt_utc, _fmt_len


def _format_button(it: dict, idx: int) -> InlineKeyboardButton:
    fmt = it.get("fmt")

    if fmt == "html_online":
        url = it.get("html_url")
        if url:
            return InlineKeyboardButton("🌐 Открыть HTML", url=url)

    if fmt == "html_local":
        return InlineKeyboardButton("📄 Скачать HTML", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "txt":
        return InlineKeyboardButton("📝 Скачать TXT", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    if fmt == "csv":
        return InlineKeyboardButton("📊 Скачать CSV", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")
    return InlineKeyboardButton("📁 Файлы", callback_data=f"{CB_HIST_FILES_PREFIX}{idx}")


# ВАЖНО: имя оставлено старым для совместимости
def build_history_page(items: list[dict], page: int, per_page: int = 1):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    idx = page
    it = items[idx]

    channel = html.escape(it.get("channel") or "—")
    dt = _fmt_dt_utc(it.get("created_at"))
    duration = _fmt_len(it.get("length_seconds"))
    msgs = it.get("messages") or 0
    users = it.get("unique_users") or 0

    text = (
        f"Канал: {channel}\n"
        f"Дата: {dt}\n"
        f"Длительность: {duration}\n"
        f"Сообщений: {msgs}\n"
        f"Пользователей: {users}"
    )

    rows = [[
        _format_button(it, idx),
        InlineKeyboardButton("🔗 Показать ссылку VOD", callback_data=f"{CB_HIST_VOD_PREFIX}{idx}")
    ]]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"{CB_HIST_PAGE}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=CB_NOOP))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"{CB_HIST_PAGE}{page + 1}"))

    if nav:
        rows.append(nav)

    kb = InlineKeyboardMarkup(rows)

    # возвращаем в старом формате совместимости
    cards = [(text, kb)]
    nav_kb = None
    return cards, nav_kb