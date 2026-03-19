from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter

from src.html_renderer import render_viewer_html
from src.html_publisher import publish_html
from src.twitch_api import (
    fetch_7tv_emote_map,
    fetch_bttv_emote_map,
    fetch_ffz_emote_map,
    fetch_twitch_global_emote_map,
    fetch_twitch_channel_emote_map,
)


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
    sent_files: List[Dict[str, str]] = []
    public_html_url: Optional[str] = None

    cdn_emotes: Dict[str, str] = {}
    combined_map: Dict[str, str] = {}

    # 7TV
    if meta.channel_id:
        m = await fetch_7tv_emote_map(session, meta.channel_id)
        twitch_channel = await fetch_twitch_channel_emote_map(session, meta.channel_id)

        combined_map.update(m)
        combined_map.update(twitch_channel)

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

    targets = set()

    for row in chat_rows:
        text = row.get("text") or ""
        for word in text.split():
            if word in combined_map:
                targets.add(word)

    # HTML ONLINE — используем CDN ссылки эмоутов
    for name in targets:
        cdn_emotes[name] = combined_map[name]

    html_text = render_viewer_html(
        chat_rows=chat_rows,
        title=(meta.title or "—"),
        channel=(meta.channel or "—"),
        vod_url=vod_url,
        created_at=meta.created_at,
        mode="online",
        channel_id=meta.channel_id,
        local_emotes={},
        cdn_emotes=cdn_emotes,
    )

    public_html_url = publish_html(html_text)

    return sent_files, public_html_url