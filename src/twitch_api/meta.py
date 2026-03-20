import asyncio
from dataclasses import dataclass
from typing import Optional, Any

import aiohttp

@dataclass
class VodMeta:
    vod_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    channel_login: Optional[str] = None
    channel_id: Optional[str] = None
    length_seconds: Optional[int] = None
    created_at: Optional[str] = None
    thumbnail_url: str | None = None


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
        thumbnailURL  
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
            meta.thumbnail_url = video.get("thumbnailURL")
            meta.title = video.get("title")
            meta.length_seconds = video.get("lengthSeconds")
            meta.created_at = video.get("createdAt")
            owner = video.get("owner") or {}
            meta.channel = owner.get("displayName") or owner.get("login")
            meta.channel_login = owner.get("login")
            meta.channel_id = owner.get("id")
            return meta
        except Exception:
            await asyncio.sleep(0.2 * (attempt + 1))
    return meta