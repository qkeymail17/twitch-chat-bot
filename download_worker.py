import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from collections import Counter

from config import OUT_DIR
from writers import PartWriterTXT, PartWriterCSV
from twitch_api import fetch_vod_meta, gql_fetch_comments, get_client_id
from ui import fmt_hhmmss

from worker_progress import make_progress_updater
from worker_writers import send_writer_file, cleanup_writer_files
from worker_html import build_html_result


async def download_and_send(
    context,
    chat_id: int,
    progress_message_id: int,
    vod_url: str,
    vod_id: str,
    fmt: str,
) -> Tuple[Dict, Dict, List[Dict[str, str]], Optional[str]]:
    client_id = get_client_id()
    session = context.application.bot_data["aiohttp"]

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

    writer = None
    chat_rows = []
    token_counter = Counter()

    if fmt == "txt":
        writer = PartWriterTXT(base_stem=base_stem, out_dir=out_dir)
    elif fmt == "csv":
        writer = PartWriterCSV(base_stem=base_stem, out_dir=out_dir)

    messages = 0
    users = set()

    progress = make_progress_updater(context, chat_id, progress_message_id, meta_dict, vod_url, fmt)

    # throttling progress updates
    last_progress_time = time.monotonic()
    progress_interval_s = 0.5
    progress_every_n = 200

    try:
        await progress(messages, len(users), done=False)

        async for offset, created_at, user, text in gql_fetch_comments(session, client_id, vod_id):
            t = fmt_hhmmss(int(offset)) if isinstance(offset, (int, float)) else "00:00:00"
            users.add(user)
            messages += 1

            if fmt == "txt":
                writer.write_line(f"[{t}] {user}: {text}")

            elif fmt == "csv":
                writer.write_row([t, created_at, user, text])

            elif fmt in ("html_online", "html_local"):
                chat_rows.append({"t": t, "user": user, "text": text})

                if fmt == "html_local":
                    cnt = token_counter
                    for tok in text.split():
                        cnt[tok] += 1

            now = time.monotonic()
            if (
                messages % progress_every_n == 0
                or now - last_progress_time >= progress_interval_s
            ):
                last_progress_time = now
                await progress(messages, len(users), done=False)

        if writer:
            writer.close()

        if messages == 0:
            raise RuntimeError("Чат пустой или Twitch не отдал комментарии.")

        await progress(messages, len(users), done=True)

        sent_files: List[Dict[str, str]] = []
        public_html_url: Optional[str] = None

        if fmt in ("txt", "csv"):
            sent_files = await send_writer_file(context, chat_id, writer)

        else:
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
                token_counter=token_counter,
            )
            meta_dict["html_url"] = public_html_url

        stats = {
            "messages": messages,
            "unique_users": len(users),
            "parts": len(sent_files),
        }

        return meta_dict, stats, sent_files, public_html_url

    finally:
        if fmt in ("txt", "csv") and writer:
            cleanup_writer_files(writer)