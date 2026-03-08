import html
from ui_formatters import fmt_hhmmss, _fmt_dt_utc, _fmt_len


def _fmt_date_ru(dt: str) -> str:
    """"YYYY-MM-DD HH:MM UTC" -> "DD Ммм YYYY HH:MM UTC" with capitalized month short name."""
    try:
        if not dt:
            return "—"
        months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
        date_part, time_part, tz = dt.split(" ")
        y, m, d = date_part.split("-")
        m_txt = months[int(m) - 1]
        return f"{int(d):02d} {m_txt} {y} {time_part} {tz}"
    except Exception:
        return dt or "—"


def build_progress_text(meta: dict, vod_url: str, fmt: str, messages: int, unique_users: int, parts: int, elapsed_s: float, done: bool) -> str:
    """
    New compact progress card.

    In-progress:
        🔄 Загрузка...
        🟣 channel
        🎬 title
        ⏱ hh:mm:ss • 💬 messages • 👥 users
        🗓 DD Ммм YYYY HH:MM UTC

    Done:
        ✅ Готово
        <same card>
    """
    title = meta.get("title") or "—"
    channel = meta.get("channel") or "—"
    # duration: display in hh:mm:ss style when available (fall back to raw or —)
    duration = _fmt_len(meta.get("length_seconds")) if meta.get("length_seconds") is not None else "—"
    # created_at — normalize via helper and localize month
    created_at_raw = _fmt_dt_utc(meta.get("created_at")) if meta.get("created_at") else None
    date_line = _fmt_date_ru(created_at_raw)

    elapsed = fmt_hhmmss(int(elapsed_s))
    status_line = "✅ Готово" if done else "🔄 Загрузка..."

    # compact stat line
    msgs = messages or 0
    users = unique_users or 0

    return (
        f"{status_line}\n"
        f"🟣 {html.escape(channel)}\n"
        f"🎬 {html.escape(title)}\n"
        f"⏱ {duration} • 💬 {msgs} • 👥 {users}\n"
        f"🗓 {date_line}"
    )


def about_text() -> str:
    return (
        "Что умеет бот:\n"
        "— Скачивает чат открытых Twitch VOD\n"
        "— Основной и самый удобный формат — 🌐 HTML-страница\n"
        "— Также доступны форматы: TXT и CSV\n\n"
        "Почему HTML лучше:\n"
        "— Открывается в браузере как страница\n"
        "— Удобный поиск по сообщениям\n"
        "— Корректно работает на телефонах и ПК\n\n"
        "⚠️ Важно для iPhone:\n"
        "HTML-файл (который скачивается документом) не открывается в iOS.\n"
        "Используй вариант «HTML-ссылка» — он работает без проблем.\n\n"
        "Как пользоваться:\n\n"
        "1. Отправь ссылку на VOD\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>\n"
        "2. Нажми кнопку нужного формата\n"
        "3. Для телефона рекомендуется 🌐 HTML-ссылка"
    )