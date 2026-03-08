def build_history_page(items: list[dict], page: int, per_page: int = 1):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))

    start = page * per_page
    it = items[start]

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

    idx = start

    kb = InlineKeyboardMarkup([[
        _format_button(it, idx),
        InlineKeyboardButton("Показать ссылку VOD", callback_data=f"{CB_HIST_VOD_PREFIX}{idx}")
    ]])

    # навигация отдельно (как ждёт main.py)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"{CB_HIST_PAGE}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=CB_NOOP))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("➡", callback_data=f"{CB_HIST_PAGE}{page + 1}"))

    nav_kb = InlineKeyboardMarkup([nav]) if nav else None

    cards = [(text, kb)]
    return cards, nav_kb