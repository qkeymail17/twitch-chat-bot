import html
from ui_formatters import fmt_hhmmss


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


def about_text() -> str:
    return (
        "Что умеет бот:\n"
        "— Скачивает чат открытого Twitch VOD в TXT / CSV / HTML\n\n"
        "Как пользоваться:\n"
        "1) Просто отправь ссылку на VOD:\n"
        "<code>https://www.twitch.tv/videos/0123456789</code>\n"
        "2) Выбери формат кнопкой"
    )