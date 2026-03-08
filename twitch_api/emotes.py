import base64
from typing import Dict

import aiohttp


async def fetch_7tv_emote_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
    """name -> URL"""
    if not channel_id:
        return {}
    try:
        url = f"https://7tv.io/v3/users/twitch/{channel_id}"
        async with session.get(url) as r:
            if r.status != 200:
                return {}
            data = await r.json()

        out: Dict[str, str] = {}
        for e in (data.get("emote_set", {}) or {}).get("emotes", []):
            name = e.get("name")
            host = (e.get("data") or {}).get("host") or {}
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


async def download_as_data_uri(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url) as r:
            if r.status != 200:
                return None
            data = await r.read()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/webp;base64,{b64}"
    except Exception:
        return None