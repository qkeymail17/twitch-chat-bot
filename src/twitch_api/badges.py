import aiohttp


async def fetch_twitch_global_badge_map(session: aiohttp.ClientSession):
    url = "https://badges.twitch.tv/v1/badges/global/display"

    async with session.get(url) as resp:
        data = await resp.json()

    result = {}

    for badge_name, badge in data.get("badge_sets", {}).items():
        for version, info in badge.get("versions", {}).items():
            key = f"{badge_name}/{version}"
            result[key] = info.get("image_url_2x") or info.get("image_url_1x")

    return result


async def fetch_twitch_channel_badge_map(session: aiohttp.ClientSession, channel_id: str):
    url = f"https://badges.twitch.tv/v1/badges/channels/{channel_id}/display"

    async with session.get(url) as resp:
        data = await resp.json()

    result = {}

    for badge_name, badge in data.get("badge_sets", {}).items():
        for version, info in badge.get("versions", {}).items():
            key = f"{badge_name}/{version}"
            result[key] = info.get("image_url_2x") or info.get("image_url_1x")

    return result