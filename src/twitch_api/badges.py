import aiohttp

CLIENT_ID = "uqdfspoy5ysdly7l52pfrcqj0nvt4a"
TOKEN = "9t6iqnf2rn43kce6twv2rhbq23k1dl"

HEADERS = {
    "Client-ID": CLIENT_ID,
    "Authorization": f"Bearer {TOKEN}",
}


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