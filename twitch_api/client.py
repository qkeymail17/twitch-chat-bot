import asyncio
import random
from typing import Any, Optional, Tuple, List, Dict

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


async def gql_post_json(session: aiohttp.ClientSession, headers: dict, payload: Any) -> Any:
    timeout = aiohttp.ClientTimeout(total=GQL_TIMEOUT_S)
    async with session.post(GQL_ENDPOINT, json=payload, headers=headers, timeout=timeout) as r:
        if r.status == 429:
            raise RuntimeError("Twitch rate limit (429)")
        if r.status >= 500:
            raise RuntimeError(f"Twitch 5xx: {r.status}")
        return await r.json()


def get_client_id() -> str:
    import os
    from config import ENV_TWITCH_CLIENT_ID
    return os.getenv(ENV_TWITCH_CLIENT_ID, DEFAULT_CLIENT_ID)