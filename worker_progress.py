import time
import asyncio

from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError
from config import PROGRESS_INTERVAL
from ui import build_progress_text


async def safe_edit_html(context, chat_id: int, message_id: int, text: str):
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
        )
    except RetryAfter as e:
        await asyncio.sleep(float(e.retry_after))
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
    except (TimedOut, NetworkError):
        return


def make_progress_updater(context, chat_id, progress_message_id, meta_dict, vod_url, fmt):
    start_t = time.monotonic()
    last_progress_t = 0.0

    async def maybe_progress(messages, users_len, done: bool = False):
        nonlocal last_progress_t
        now = time.monotonic()
        if (not done) and (now - last_progress_t < PROGRESS_INTERVAL):
            return
        last_progress_t = now

        parts = 1 if fmt in ("txt", "csv", "html_local") else 0

        text = build_progress_text(
            meta=meta_dict,
            vod_url=vod_url,
            fmt=fmt,
            messages=messages,
            unique_users=users_len,
            parts=parts,
            elapsed_s=now - start_t,
            done=done,
        )
        await safe_edit_html(context, chat_id, progress_message_id, text)

    return maybe_progress