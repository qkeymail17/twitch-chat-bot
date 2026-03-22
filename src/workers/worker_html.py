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
    fetch_twitch_channel_emote_maps,
    fetch_twitch_global_badge_map,
    fetch_twitch_channel_badge_map,
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
    twitch_emote_id_map: Dict[str, str] = {}
    badge_images: Dict[str, str] = {}

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
        name_map, id_map = await fetch_twitch_channel_emote_maps(session, meta.channel_id)
        combined_map.update(name_map)
        twitch_emote_id_map.update(id_map)
        # Channel/subscriber emotes should be available even if the text scan misses
        # a token boundary or the row has no fragment metadata.
        cdn_emotes.update(name_map)
        cdn_emotes.update(id_map)

    # Twitch badges
    badge_images.update(await fetch_twitch_global_badge_map(session))
    if meta.channel_id:
        badge_images.update(await fetch_twitch_channel_badge_map(session, str(meta.channel_id)))

    targets = set()
    targets_by_id = set()

    for row in chat_rows:
        text = row.get("text") or ""
        for word in text.split():
            if word in combined_map:
                targets.add(word)

        for fragment in row.get("fragments") or []:
            if not isinstance(fragment, dict):
                continue
            frag_text = (fragment.get("text") or "").strip()
            if frag_text and frag_text in combined_map:
                targets.add(frag_text)

            emote = fragment.get("emote") or {}
            if isinstance(emote, dict):
                emote_id = emote.get("emoteID") or emote.get("id")
                if emote_id and str(emote_id) in twitch_emote_id_map:
                    targets_by_id.add(str(emote_id))

    # HTML ONLINE — используем CDN ссылки эмоутов
    for name in targets:
        cdn_emotes[name] = combined_map[name]
    for emote_id in targets_by_id:
        cdn_emotes[emote_id] = twitch_emote_id_map[emote_id]

    html_text = render_viewer_html(
        chat_rows=chat_rows,
        title=(meta.title or "—"),
        channel=(meta.channel or "—"),
        vod_url=vod_url,
        created_at=meta.created_at,
        thumbnail_url=meta.thumbnail_url,
        mode="online",
        channel_id=meta.channel_id,
        local_emotes={},
        cdn_emotes=cdn_emotes,
        badge_images=badge_images,
    )

    public_html_url = publish_html(html_text)

    return sent_files, public_html_url