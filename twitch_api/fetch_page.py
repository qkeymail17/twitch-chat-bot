from typing import Optional, Any, Dict, List, Tuple
import aiohttp

from .client import gql_post_json

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
            "persistedQuery": {"version": 1, "sha256Hash": VIDEO_COMMENTS_HASH},
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