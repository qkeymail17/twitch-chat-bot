import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional

from src.config import OUT_DIR
from src.twitch_api import fetch_vod_meta, gql_fetch_comments, get_client_id
from src.ui.ui import fmt_hhmmss

from .worker_progress import make_progress_updater
from .worker_html import build_html_result

from src.handlers.handlers_state import is_cancelled, clear_cancel


async def download_and_send(
    context,
    chat_id: int,
    progress_message_id: int,
    vod_url: str,
    vod_id: str,
    fmt: str,
) -> Tuple[Dict, Dict, List[Dict[str, str]], Optional[str]]:
    session = context.application.bot_data["aiohttp"]

    client_id = get_client_id()

    meta = await fetch_vod_meta(session, client_id, vod_id)
    meta_dict = {
        "title": meta.title,
        "channel": meta.channel,
        "length_seconds": meta.length_seconds,
        "vod_len": fmt_hhmmss(int(meta.length_seconds)) if isinstance(meta.length_seconds, int) else "—",
        "created_at": meta.created_at,
    }

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(exist_ok=True)

    safe_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_stem = f"vod_{vod_id}_{safe_ts}_{fmt}"

    chat_rows = []

    messages = 0
    users = set()

    progress = make_progress_updater(context, chat_id, progress_message_id, meta_dict, vod_url, fmt)

    last_progress_time = time.monotonic()
    progress_interval_s = 0.5
    progress_every_n = 200

    try:
        await progress(messages, len(users), done=False)

        comment_iter = gql_fetch_comments(session, client_id, vod_id)

        try:
            first = await asyncio.wait_for(comment_iter.__anext__(), timeout=10)
        except StopAsyncIteration:
            raise RuntimeError("CHAT_EMPTY")
        except asyncio.TimeoutError:
            raise RuntimeError("CHAT_EMPTY")

        offset, created_at, user, text = first

        t = fmt_hhmmss(int(offset)) if isinstance(offset, (int, float)) else "00:00:00"

        users.add(user)
        messages += 1

        chat_rows.append({
            "t": t,
            "user": user,
            "text": text
        })

        async for offset, created_at, user, text in comment_iter:

            if is_cancelled(context):
                raise RuntimeError("Загрузка была отменена.")

            t = fmt_hhmmss(int(offset)) if isinstance(offset, (int, float)) else "00:00:00"

            users.add(user)
            messages += 1

            chat_rows.append({
                "t": t,
                "user": user,
                "text": text
            })

            now = time.monotonic()
            if (
                    messages % progress_every_n == 0
                    or now - last_progress_time >= progress_interval_s
            ):
                last_progress_time = now
                await progress(messages, len(users), done=False)

        if messages == 0:
            raise RuntimeError("Чат пустой или Twitch не отдал комментарии.")

        await progress(messages, len(users), done=True)

        sent_files: List[Dict[str, str]] = []
        public_html_url: Optional[str] = None

        sent_files, public_html_url = await build_html_result(
            context=context,
            session=session,
            chat_id=chat_id,
            fmt=fmt,
            meta=meta,
            vod_url=vod_url,
            base_stem=base_stem,
            out_dir=out_dir,
            chat_rows=chat_rows,
            token_counter=None,
        )

        meta_dict["html_url"] = public_html_url

        stats = {
            "messages": messages,
            "unique_users": len(users),
            "parts": len(sent_files),
        }

        return meta_dict, stats, sent_files, public_html_url

    finally:
        clear_cancel(context)