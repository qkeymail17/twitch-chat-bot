import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp

from src.config import TWITCH_CLIENT_ID, TWITCH_ACCESS_TOKEN

async def resolve_thumbnail(session, thumb_template):
    sizes = [
        (1920, 1080),
        (1280, 720),
        (640, 360),
        (480, 270),
    ]

    for w, h in sizes:
        url = thumb_template.replace("%{width}", str(w)).replace("%{height}", str(h))
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return url
        except:
            continue

    return thumb_template.replace("%{width}", "480").replace("%{height}", "270")

@dataclass
class VodMeta:
    vod_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    channel_login: Optional[str] = None
    channel_id: Optional[str] = None
    length_seconds: Optional[int] = None
    created_at: Optional[str] = None

    thumbnail_preview_url: Optional[str] = None
    thumbnail_full_url: Optional[str] = None


def extract_user_color(node: dict) -> Optional[str]:
    msg = node.get("message") or {}
    color = (
        msg.get("userColor")
        or msg.get("userColorHex")
        or node.get("userColor")
        or node.get("userColorHex")
    )
    if not color:
        return None
    color = str(color).strip()
    return color or None


def extract_user_badges(node: dict) -> list[dict]:
    msg = node.get("message") or {}
    raw_badges = msg.get("userBadges") or node.get("userBadges") or []
    out: list[dict] = []

    for badge in raw_badges:
        if not isinstance(badge, dict):
            continue

        set_id = (
            badge.get("setID")
            or badge.get("setId")
            or badge.get("set_id")
            or badge.get("set")
        )
        version = (
            badge.get("version")
            or badge.get("id")
            or badge.get("badgeVersion")
            or badge.get("badge_version")
        )

        if set_id is None or version is None:
            continue

        out.append({
            "set_id": str(set_id),
            "version": str(version),
        })

    return out


def extract_message_fragments(node: dict) -> list[dict]:
    msg = node.get("message") or {}
    fragments = msg.get("fragments") or []

    out: list[dict] = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue

        item = {"text": fragment.get("text") or ""}
        emote = fragment.get("emote") or {}
        if isinstance(emote, dict):
            emote_id = emote.get("emoteID") or emote.get("id")
            if emote_id:
                item["emoteID"] = emote_id
            emote_name = emote.get("name")
            if emote_name:
                item["emoteName"] = emote_name

        out.append(item)

    return out


def render_message(node: dict) -> str:
    fragments = extract_message_fragments(node)
    return "".join((f.get("text") or "") for f in fragments).strip()


async def fetch_vod_meta(session: aiohttp.ClientSession, client_id: str, vod_id: str) -> VodMeta:
    from .client import gql_post_json
    headers = {
        "Client-Id": client_id,
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
    }
    query = """
    query($id: ID!) {
      video(id: $id) {
        id
        title
        lengthSeconds
        createdAt
        owner {
          id
          login
          displayName
        }
      }
    }
    """
    meta = VodMeta(vod_id=vod_id)
    for attempt in range(3):
        try:
            payload = {"query": query, "variables": {"id": vod_id}}
            data = await gql_post_json(session, headers, payload)
            video = ((data.get("data") or {}).get("video") or {})
            meta.title = video.get("title")
            meta.length_seconds = video.get("lengthSeconds")
            meta.created_at = video.get("createdAt")
            owner = video.get("owner") or {}
            meta.channel = owner.get("displayName") or owner.get("login")
            meta.channel_login = owner.get("login")
            meta.channel_id = owner.get("id")

            try:
                helix_url = f"https://api.twitch.tv/helix/videos?id={vod_id}"
                helix_headers = {
                    "Client-Id": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}",
                }

                async with session.get(helix_url, headers=helix_headers) as resp:
                    data2 = await resp.json()
                    videos = data2.get("data") or []
                    if videos:
                        thumb = videos[0].get("thumbnail_url")
                        if thumb:
                            preview = thumb.replace("%{width}", "480").replace("%{height}", "270")
                            full = await resolve_thumbnail(session, thumb)

                            meta.thumbnail_preview_url = preview
                            meta.thumbnail_full_url = full or preview
            except Exception:
                pass

            return meta
        except Exception:
            await asyncio.sleep(0.2 * (attempt + 1))
    return meta