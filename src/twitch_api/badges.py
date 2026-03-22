import aiohttp

HEADERS = {
    "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko",
}


async def fetch_twitch_global_badge_map(session: aiohttp.ClientSession):
    url = "https://api.twitch.tv/helix/chat/badges/global"

    async with session.get(url) as resp:
        data = await resp.json()

    result = {}

    for badge_name, badge in data.get("badge_sets", {}).items():
        for version, info in badge.get("versions", {}).items():
            key = f"{badge_name}/{version}"
            result[key] = info.get("image_url_2x") or info.get("image_url_1x")

    return result


async def fetch_twitch_channel_badge_map(session: aiohttp.ClientSession, channel_id: str):
    url = f"https://api.twitch.tv/helix/chat/badges?broadcaster_id={channel_id}"

    async with session.get(url, headers=HEADERS) as resp:
        data = await resp.json()

        result = {}

        for badge in data.get("data", []):
            set_id = badge.get("set_id")
            for version in badge.get("versions", []):
                key = f"{set_id}/{version.get('id')}"
                result[key] = version.get("image_url_2x") or version.get("image_url_1x")

    return result