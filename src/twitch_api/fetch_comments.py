import asyncio
import random
from src.config import FETCH_DELAY_BASE, FETCH_DELAY_MAX, GQL_MAX_RETRIES
from typing import Optional, List

import aiohttp

from .fetch_page import gql_fetch_page
from .meta import render_message, extract_message_fragments, extract_user_color, extract_user_badges, extract_reply_meta


async def gql_fetch_comments(
    session: aiohttp.ClientSession,
    client_id: str,
    vod_id: str,
    start_offset: int = 0,
):
    """yields (offset_seconds, created_at_iso, display_name, message_text, fragments, color, badges)"""
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
                delay_s = max(FETCH_DELAY_BASE * 0.35, delay_s * 0.75)
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
            fragments = extract_message_fragments(node)
            text = render_message(node)
            color = extract_user_color(node)
            badges = extract_user_badges(node)
            reply = extract_reply_meta(node)

            print("REPLY RAW:", node.get("message", {}).get("reply"))
            if text:
                yield (offset, created_at, display, text, fragments, color, badges, reply)

        if not has_next or not next_cursor:
            return
        cursor = next_cursor

        if delay_s > FETCH_DELAY_BASE * 0.4:
            await asyncio.sleep(delay_s)