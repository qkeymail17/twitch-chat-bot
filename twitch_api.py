import asyncio
import random
from dataclasses import dataclass
from typing import Optional, Any, Tuple, List, Dict

import aiohttp

from config import (
    GQL_ENDPOINT,
    VIDEO_COMMENTS_HASH,
    DEFAULT_CLIENT_ID,
    FETCH_DELAY_BASE,
    FETCH_DELAY_MAX,
    GQL_MAX_RETRIES,
    GQL_TIMEOUT_S,
)


@dataclass
class VodMeta:
    vod_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    channel_login: Optional[str] = None
    channel_id: Optional[str] = None
    length_seconds: Optional[int] = None
    created_at: Optional[str] = None


def render_message(node: dict) -> str:
    msg = node.get("message") or {}
    fragments = msg.get("fragments") or []
    return "".join((f.get("text") or "") for f in fragments).strip()


async def gql_post_json(session: aiohttp.ClientSession, headers: dict, payload: Any) -> Any:
    timeout = aiohttp.ClientTimeout(total=GQL_TIMEOUT_S)
    async with session.post(GQL_ENDPOINT, json=payload, headers=headers, timeout=timeout) as r:
        if r.status == 429:
            raise RuntimeError("Twitch rate limit (429)")
        if r.status >= 500:
            raise RuntimeError(f"Twitch 5xx: {r.status}")
        return await r.json()


async def fetch_vod_meta(session: aiohttp.ClientSession, client_id: str, vod_id: str) -> VodMeta:
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
            return meta
        except Exception:
            await asyncio.sleep(0.2 * (attempt + 1))

    return meta


async def gql_fetch_page(
    session: aiohttp.ClientSession,
    client_id: str,
    vod_id: str,
    cursor: Optional[str],
    start_offset: int,
) -> Tuple[List[dict], Optional[str], bool]:
    headers = {
        "Client-Id": client_id,
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
    }

    variables: Dict[str, Any] = {"videoID": vod_id}
    if cursor:
        variables["cursor"] = cursor
    else:
        variables["contentOffsetSeconds"] = int(start_offset)

    payload = [{
        "operationName": "VideoCommentsByOffsetOrCursor",
        "variables": variables,
        "extensions": {
            "persistedQuery": {"version": 1, "sha256Hash": VIDEO_COMMENTS_HASH}
        },
    }]

    data = await gql_post_json(session, headers, payload)

    item = data[0] if isinstance(data, list) and data else {}
    video = ((item.get("data") or {}).get("video") or {})
    comments = (video.get("comments") or {})
    edges = comments.get("edges") or []
    page_info = comments.get("pageInfo") or {}
    has_next = bool(page_info.get("hasNextPage"))
    next_cursor = edges[-1].get("cursor") if edges else None
    return edges, next_cursor, has_next


async def gql_fetch_comments(
    session: aiohttp.ClientSession,
    client_id: str,
    vod_id: str,
    start_offset: int = 0,
):
    """
    yields (offset_seconds, created_at_iso, display_name, message_text)
    """
    cursor = None
    delay_s = FETCH_DELAY_BASE

    while True:
        edges: List[dict] = []
        next_cursor: Optional[str] = None
        has_next = False

        for attempt in range(GQL_MAX_RETRIES):
            try:
                edges, next_cursor, has_next = await gql_fetch_page(
                    session=session,
                    client_id=client_id,
                    vod_id=vod_id,
                    cursor=cursor,
                    start_offset=start_offset,
                )
                delay_s = max(FETCH_DELAY_BASE, delay_s * 0.9)
                break
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                if attempt == GQL_MAX_RETRIES - 1:
                    raise RuntimeError(f"Twitch API error after retries: {e}") from e
                delay_s = min(FETCH_DELAY_MAX, max(delay_s * 1.6, 0.15))
                await asyncio.sleep(delay_s + random.uniform(0, 0.2))

        if not edges:
            return

        for edge in edges:
            node = edge.get("node") or {}
            commenter = node.get("commenter") or {}
            display = commenter.get("displayName") or commenter.get("login") or "unknown"
            offset = node.get("contentOffsetSeconds")
            created_at = node.get("createdAt") or ""
            text = render_message(node)
            if text:
                yield (offset, created_at, display, text)

        if not has_next or not next_cursor:
            return

        cursor = next_cursor
        await asyncio.sleep(delay_s)


def get_client_id() -> str:
    import os
    from config import ENV_TWITCH_CLIENT_ID
    return os.getenv(ENV_TWITCH_CLIENT_ID, DEFAULT_CLIENT_ID)

import base64

async def fetch_7tv_emote_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
    """
    name -> webp url
    """
    if not channel_id:
        return {}

    try:
        url = f"https://7tv.io/v3/users/twitch/{channel_id}"
        async with session.get(url) as r:
            if r.status != 200:
                return {}

            data = await r.json()

        emotes = data.get("emote_set", {}).get("emotes", [])

        out = {}

        for e in emotes:
            name = e.get("name")
            host = e.get("data", {}).get("host", {})

            if not name or not host:
                continue

            files = host.get("files") or []

            file = None
            for f in files:
                if f.get("name") == "1x.webp":
                    file = f
                    break

            if not file and files:
                file = files[0]

            if not file:
                continue

            out[name] = f"https:{host['url']}/{file['name']}"

        return out

    except Exception:
        return {}


async def download_as_data_uri(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url) as r:
            if r.status != 200:
                return None
            data = await r.read()

        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/webp;base64,{b64}"

    except Exception:
        return None