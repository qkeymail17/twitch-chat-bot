import base64
from typing import Dict
from .twitch_global_emotes import TWITCH_GLOBAL_EMOTES

import aiohttp


# =========================
# 7TV
# =========================

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


# =========================
# BTTV
# =========================

async def fetch_bttv_emote_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
    """BTTV global + channel emotes"""
    out: Dict[str, str] = {}
    try:
        # global
        async with session.get("https://api.betterttv.net/3/cached/emotes/global") as r:
            if r.status == 200:
                data = await r.json()
                for e in data:
                    out[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/1x"

        if not channel_id:
            return out

        # channel
        async with session.get(f"https://api.betterttv.net/3/cached/users/twitch/{channel_id}") as r:
            if r.status != 200:
                return out
            data = await r.json()

        for e in data.get("channelEmotes", []):
            out[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/1x"
        for e in data.get("sharedEmotes", []):
            out[e["code"]] = f"https://cdn.betterttv.net/emote/{e['id']}/1x"

        return out
    except Exception:
        return out


# =========================
# FFZ
# =========================

async def fetch_ffz_emote_map(session: aiohttp.ClientSession, channel_name: str) -> Dict[str, str]:
    """FFZ global + channel emotes"""
    out: Dict[str, str] = {}
    try:
        # global
        async with session.get("https://api.frankerfacez.com/v1/set/global") as r:
            if r.status == 200:
                data = await r.json()
                sets = data.get("sets", {})
                for s in sets.values():
                    for e in s.get("emoticons", []):
                        urls = e.get("urls", {})
                        url = urls.get("1") or urls.get("2") or urls.get("4")
                        if url:
                            out[e["name"]] = "https:" + url

        if not channel_name:
            return out

        # channel
        async with session.get(f"https://api.frankerfacez.com/v1/room/{channel_name}") as r:
            if r.status != 200:
                return out
            data = await r.json()

        sets = data.get("sets", {})
        for s in sets.values():
            for e in s.get("emoticons", []):
                urls = e.get("urls", {})
                url = urls.get("1") or urls.get("2") or urls.get("4")
                if url:
                    out[e["name"]] = "https:" + url

        return out
    except Exception:
        return out


# =========================
# Twitch Global (dictionary-based)
# =========================

async def fetch_twitch_global_emote_map(session: aiohttp.ClientSession) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, eid in TWITCH_GLOBAL_EMOTES.items():
        out[name] = f"https://static-cdn.jtvnw.net/emoticons/v2/{eid}/default/dark/1.0"
    return out


# =========================
# Twitch Channel (Subscriber via twitchemotes)
# =========================

async def fetch_twitch_channel_emote_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
    """Twitch subscriber emotes (unofficial via twitchemotes.com)"""
    if not channel_id:
        return {}

    out: Dict[str, str] = {}

    try:
        url = f"https://twitchemotes.com/channels/{channel_id}"
        async with session.get(url) as r:
            if r.status != 200:
                return {}
            html = await r.text()

        # Ищем все вхождения вида:
        # <img src="https://static-cdn.jtvnw.net/emoticons/v1/EMOTE_ID/1.0" ... alt="EMOTE_NAME">
        import re

        pattern = re.compile(
            r'<img[^>]+src="https://static-cdn\.jtvnw\.net/emoticons/v1/(\d+)/1\.0"[^>]+alt="([^"]+)"',
            re.IGNORECASE
        )

        for emote_id, name in pattern.findall(html):
            out[name] = f"https://static-cdn.jtvnw.net/emoticons/v1/{emote_id}/1.0"

        return out

    except Exception:
        return {}


# =========================
# Downloader (общий)
# =========================

async def download_as_data_uri(session: aiohttp.ClientSession, url: str):
    try:
        async with session.get(url) as r:
            if r.status != 200:
                return None
            data = await r.read()

        mime = "image/webp"
        if url.endswith(".gif"):
            mime = "image/gif"
        elif url.endswith(".png"):
            mime = "image/png"

        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None