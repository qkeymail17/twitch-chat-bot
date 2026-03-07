import time
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from collections import Counter

from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError

from config import OUT_DIR, MAX_PART_BYTES, PROGRESS_INTERVAL
from writers import PartWriterTXT, PartWriterCSV
from html_renderer import render_viewer_html
from html_publisher import publish_html
from twitch_api import fetch_vod_meta, gql_fetch_comments, get_client_id, fetch_7tv_emote_map, download_as_data_uri
from ui import fmt_hhmmss, build_progress_text


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


async def download_and_send(
    context,
    chat_id: int,
    progress_message_id: int,
    vod_url: str,
    vod_id: str,
    fmt: str,
) -> Tuple[Dict, Dict, List[Dict[str, str]], Optional[str]]:
    """
    Returns: (meta_dict, stats_dict, files_list(file_id + file_name), public_html_url)
    fmt: txt/csv/html_online/html_local
    """
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
    chat_rows = []  # for HTML
    token_counter = Counter()
    public_html_url = None

    if fmt == "txt":
        writer = PartWriterTXT(base_stem=base_stem, out_dir=out_dir, max_bytes=MAX_PART_BYTES)
    elif fmt == "csv":
        writer = PartWriterCSV(base_stem=base_stem, out_dir=out_dir, max_bytes=MAX_PART_BYTES)

    messages = 0
    users = set()

    start_t = time.monotonic()
    last_progress_t = 0.0

    async def maybe_progress(done: bool = False):
        nonlocal last_progress_t
        now = time.monotonic()
        if (not done) and (now - last_progress_t < PROGRESS_INTERVAL):
            return
        last_progress_t = now

        parts = 1
        if fmt in ("txt", "csv"):
            parts = len(writer.paths) if writer and writer.paths else (1 if messages > 0 else 0)

        text = build_progress_text(
            meta=meta_dict,
            vod_url=vod_url,
            fmt=fmt,
            messages=messages,
            unique_users=len(users),
            parts=parts,
            elapsed_s=now - start_t,
            done=done,
        )
        await safe_edit_html(context, chat_id, progress_message_id, text)

    try:
        await maybe_progress(done=False)

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
                    for tok in text.split():
                        token_counter[tok] += 1

            await maybe_progress(done=False)

        if writer:
            writer.close()

        if messages == 0:
            raise RuntimeError("Чат пустой или Twitch не отдал комментарии.")

        await maybe_progress(done=True)

        sent_files: List[Dict[str, str]] = []

        if fmt in ("txt", "csv"):
            for p in writer.paths:
                with p.open("rb") as f:
                    msg = await context.bot.send_document(chat_id=chat_id, document=f, filename=p.name)
                if msg and msg.document:
                    sent_files.append({"file_id": msg.document.file_id, "file_name": p.name})
        else:
            local_emotes = {}

            if fmt == "html_local" and meta.channel_id:
                emote_map = await fetch_7tv_emote_map(session, meta.channel_id)

                top = [t for t, _ in token_counter.most_common(1500)]
                targets = [t for t in top if t in emote_map]

                for name in targets:
                    uri = await download_as_data_uri(session, emote_map[name])
                    if uri:
                        local_emotes[name] = uri

            html_text = render_viewer_html(
                chat_rows=chat_rows,
                title=(meta.title or "—"),
                channel=(meta.channel or "—"),
                vod_url=vod_url,
                created_at=meta.created_at,
                mode=("online" if fmt == "html_online" else "local"),
                channel_id=meta.channel_id,
                local_emotes=local_emotes,
            )
            html_path = out_dir / f"{base_stem}.html"
            html_path.write_text(html_text, encoding="utf-8")

            if fmt == "html_online":
                public_html_url = publish_html(html_text)
                meta_dict["html_url"] = public_html_url  # ← ключевая правка

            with html_path.open("rb") as f:
                msg = await context.bot.send_document(chat_id=chat_id, document=f, filename=html_path.name)
            if msg and msg.document:
                sent_files.append({"file_id": msg.document.file_id, "file_name": html_path.name})

        stats = {
            "messages": messages,
            "unique_users": len(users),
            "parts": len(sent_files),
        }

        return meta_dict, stats, sent_files, public_html_url

    finally:
        try:
            if fmt in ("txt", "csv") and writer:
                for p in getattr(writer, "paths", []):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass