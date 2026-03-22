import base64
import logging
from typing import Dict, Tuple

import aiohttp

from .client import get_api_headers


# =========================
# 7TV
# =========================

async def fetch_7tv_emote_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
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
    out: Dict[str, str] = {}
    try:
        async with session.get("https://api.betterttv.net/3/cached/emotes/global") as r:
            if r.status == 200:
                data = await r.json()
                for e in data:
                    out[e["code"]] = f"https://images.weserv.nl/?url=cdn.betterttv.net/emote/{e['id']}/1x"

        if not channel_id:
            return out

        async with session.get(f"https://api.betterttv.net/3/cached/users/twitch/{channel_id}") as r:
            if r.status != 200:
                return out
            data = await r.json()

        for e in data.get("channelEmotes", []):
            out[e["code"]] = f"https://images.weserv.nl/?url=cdn.betterttv.net/emote/{e['id']}/1x"
        for e in data.get("sharedEmotes", []):
            out[e["code"]] = f"https://images.weserv.nl/?url=cdn.betterttv.net/emote/{e['id']}/1x"

        return out
    except Exception:
        return out


# =========================
# FFZ
# =========================

async def fetch_ffz_emote_map(session: aiohttp.ClientSession, channel_name: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
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
# Twitch Global (HELIX)
# =========================

async def fetch_twitch_global_emote_map(session: aiohttp.ClientSession) -> Dict[str, str]:
    url = "https://api.twitch.tv/helix/chat/emotes/global"
    headers = get_api_headers()

    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                logging.warning("Twitch global emotes HTTP %s", resp.status)
                return {}
            data = await resp.json()
    except Exception as e:
        logging.warning("Twitch global emotes error: %s", e)
        return {}

    out: Dict[str, str] = {}

    for e in data.get("data", []) or []:
        name = e.get("name")
        emote_id = e.get("id")
        if not name or not emote_id:
            continue

        out[name] = f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/1.0"

    return out


# =========================
# Twitch Badges
# =========================

async def _fetch_twitch_badge_map(session: aiohttp.ClientSession, url: str) -> Dict[str, str]:
    headers = get_api_headers()

    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                logging.warning("Twitch badges HTTP %s for %s", resp.status, url)
                return {}
            data = await resp.json()
    except Exception as e:
        logging.warning("Twitch badges error for %s: %s", url, e)
        return {}

    out: Dict[str, str] = {}

    for badge_set in data.get("data", []) or []:
        set_id = str(badge_set.get("set_id") or "").strip().lower()
        if not set_id:
            continue

        for version in badge_set.get("versions", []) or []:
            version_id = str(version.get("id") or "").strip()
            if not version_id:
                continue
            image = (
                version.get("image_url_1x")
                or version.get("image_url_2x")
                or version.get("image_url_4x")
            )
            if image:
                out[f"{set_id}:{version_id}"] = image

    return out


async def fetch_twitch_global_badge_map(session: aiohttp.ClientSession) -> Dict[str, str]:
    return await _fetch_twitch_badge_map(session, "https://api.twitch.tv/helix/chat/badges/global")


async def fetch_twitch_channel_badge_map(session: aiohttp.ClientSession, channel_id: str) -> Dict[str, str]:
    if not channel_id:
        return {}
    return await _fetch_twitch_badge_map(session, f"https://api.twitch.tv/helix/chat/badges?broadcaster_id={channel_id}")


# =========================
# Twitch Channel
# =========================

async def fetch_twitch_channel_emote_maps(
    session: aiohttp.ClientSession,
    channel_id: str,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    if not channel_id:
        return {}, {}

    url = f"https://api.twitch.tv/helix/chat/emotes?broadcaster_id={channel_id}"
    headers = get_api_headers()

    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                logging.warning("Twitch channel emotes HTTP %s", resp.status)
                return {}, {}
            data = await resp.json()
    except Exception as e:
        logging.warning("Twitch channel emotes error: %s", e)
        return {}, {}

    name_map: Dict[str, str] = {}
    id_map: Dict[str, str] = {}

    for e in data.get("data", []) or []:
        name = e.get("name")
        emote_id = e.get("id")
        images = e.get("images") or {}
        src = images.get("url_1x")

        if not src and emote_id:
            src = f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/1.0"

        if name and src:
            name_map[name] = src
        if emote_id and src:
            id_map[str(emote_id)] = src

    return name_map, id_map