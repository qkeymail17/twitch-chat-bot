from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import Counter

from html_renderer import render_viewer_html
from html_publisher import publish_html
from twitch_api import (
    fetch_7tv_emote_map,
    fetch_bttv_emote_map,
    fetch_ffz_emote_map,
    fetch_twitch_global_emote_map,
    fetch_twitch_channel_emote_map,
    download_as_data_uri,
)
import logging

async def build_html_result(
    context,
    session,
    chat_id: int,
    fmt: str,
    meta,
    vod_url: str,
    base_stem: str,
    out_dir: Path,
    chat_rows: List[Dict],
    token_counter: Counter,
):
    logging.warning(f"CHANNEL_ID DEBUG: {meta.channel_id} ({type(meta.channel_id)})")
    sent_files: List[Dict[str, str]] = []
    public_html_url: Optional[str] = None
    local_emotes = {}
    cdn_emotes: Dict[str, str] = {}

    combined_map: Dict[str, str] = {}

    # 7TV
    if meta.channel_id:
        m = await fetch_7tv_emote_map(session, meta.channel_id)
        combined_map.update(m)

    # BTTV
    if meta.channel_id:
        m = await fetch_bttv_emote_map(session, meta.channel_id)
        combined_map.update(m)

    # FFZ
    if meta.channel:
        m = await fetch_ffz_emote_map(session, meta.channel)
        combined_map.update(m)

    # Twitch Global
    m = await fetch_twitch_global_emote_map(session)
    combined_map.update(m)

    # Twitch Channel
    if meta.channel_id:
        m = await fetch_twitch_channel_emote_map(session, meta.channel_id)
        combined_map.update(m)

    targets = set()

    for row in chat_rows:
        text = row.get("text") or ""
        for word in text.split():
            if word in combined_map:
                targets.add(word)

    if fmt == "html_local":
        for name in targets:
            uri = await download_as_data_uri(session, combined_map[name])
            if uri:
                local_emotes[name] = uri

    if fmt == "html_online":
        for name in targets:
            cdn_emotes[name] = combined_map[name]

    html_text = render_viewer_html(
        chat_rows=chat_rows,
        title=(meta.title or "—"),
        channel=(meta.channel or "—"),
        vod_url=vod_url,
        created_at=meta.created_at,
        mode=("online" if fmt == "html_online" else "local"),
        channel_id=meta.channel_id,
        local_emotes=local_emotes,
        cdn_emotes=cdn_emotes,
    )

    if fmt == "html_online":
        public_html_url = publish_html(html_text)

    elif fmt == "html_local":
        html_path = out_dir / f"{base_stem}.html"
        html_path.write_text(html_text, encoding="utf-8")

        with html_path.open("rb") as f:
            msg = await context.bot.send_document(chat_id=chat_id, document=f, filename=html_path.name)
        if msg and msg.document:
            sent_files.append({"file_id": msg.document.file_id, "file_name": html_path.name})
            await msg.delete()

    return sent_files, public_html_url