import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp

from src.config import TWITCH_CLIENT_ID, TWITCH_ACCESS_TOKEN

@dataclass
class VodMeta:
    vod_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    channel_login: Optional[str] = None
    channel_id: Optional[str] = None
    length_seconds: Optional[int] = None
    created_at: Optional[str] = None
    thumbnail_url: Optional[str] = None


def extract_user_color(node: dict) -> Optional[str]:
    msg = node.get("message") or {}
    color = (
        msg.get("userColor")
        or msg.get("userColorHex")
        or node.get("userColor")
        or node.get("userColorHex")
    )
    if not color:
        return None
    color = str(color).strip()
    return color or None


def extract_user_badges(node: dict) -> list[dict]:
    msg = node.get("message") or {}
    raw_badges = msg.get("userBadges") or node.get("userBadges") or []
    out: list[dict] = []

    for badge in raw_badges:
        if not isinstance(badge, dict):
            continue

        set_id = (
            badge.get("setID")
            or badge.get("setId")
            or badge.get("set_id")
            or badge.get("set")
        )
        version = (
            badge.get("version")
            or badge.get("id")
            or badge.get("badgeVersion")
            or badge.get("badge_version")
        )

        if set_id is None or version is None:
            continue

        out.append({
            "set_id": str(set_id),
            "version": str(version),
        })

    return out


def extract_reply_meta(node: dict) -> Optional[dict]:
    msg = node.get("message") or {}
    candidate_keys = (
        "reply",
        "parent",
        "parentMessage",
        "parentComment",
        "replyParent",
        "reply_parent",
        "replyTo",
        "reply_to",
        "repliedTo",
        "replied_to",
        "sourceMessage",
        "originalMessage",
        "original_message",
    )

    def _normalize_comment_like(comment: dict) -> Optional[dict]:
        if not isinstance(comment, dict):
            return None

        commenter = comment.get("commenter") or comment.get("author") or comment.get("user") or {}
        if not isinstance(commenter, dict):
            commenter = {}

        display = (
            comment.get("displayName")
            or comment.get("display_name")
            or comment.get("login")
            or commenter.get("displayName")
            or commenter.get("display_name")
            or commenter.get("login")
            or ""
        )
        login = (
            commenter.get("login")
            or comment.get("login")
            or comment.get("userLogin")
            or comment.get("user_login")
            or ""
        )
        text = render_message(comment).strip() or str(comment.get("body") or comment.get("text") or "").strip()
        color = extract_user_color(comment)
        badges = extract_user_badges(comment)

        if not display and not login and not text:
            return None

        return {
            "user": str(display or login or "unknown"),
            "login": str(login or ""),
            "text": text,
            "color": color,
            "badges": badges,
            "id": comment.get("id") or comment.get("messageID") or comment.get("commentID"),
        }

    # First try direct nested reply/comment objects.
    for source in (msg, node):
        if not isinstance(source, dict):
            continue

        for key in candidate_keys:
            candidate = source.get(key)
            if isinstance(candidate, dict):
                reply = _normalize_comment_like(candidate)
                if reply and (reply.get("user") or reply.get("text")):
                    return reply

    # Then try scalar fields commonly used by Twitch payloads.
    display = (
        msg.get("replyParentDisplayName")
        or msg.get("replyParentUserDisplayName")
        or msg.get("replyParentLogin")
        or msg.get("replyParentUserLogin")
        or node.get("replyParentDisplayName")
        or node.get("replyParentUserDisplayName")
        or node.get("replyParentLogin")
        or node.get("replyParentUserLogin")
        or ""
    )
    login = (
        msg.get("replyParentLogin")
        or msg.get("replyParentUserLogin")
        or node.get("replyParentLogin")
        or node.get("replyParentUserLogin")
        or ""
    )
    text = (
        msg.get("replyParentMessageBody")
        or msg.get("replyParentMessageText")
        or msg.get("replyParentBody")
        or msg.get("replyParentText")
        or node.get("replyParentMessageBody")
        or node.get("replyParentMessageText")
        or node.get("replyParentBody")
        or node.get("replyParentText")
        or ""
    )
    color = (
        msg.get("replyParentUserColor")
        or msg.get("replyParentUserColorHex")
        or node.get("replyParentUserColor")
        or node.get("replyParentUserColorHex")
        or None
    )
    reply_id = (
        msg.get("replyParentMessageID")
        or msg.get("replyParentMessageId")
        or node.get("replyParentMessageID")
        or node.get("replyParentMessageId")
        or None
    )

    if display or login or text or color or reply_id:
        reply = {
            "user": str(display or login or "unknown"),
            "login": str(login or ""),
            "text": str(text or "").strip(),
            "color": str(color).strip() if color else None,
            "badges": [],
            "id": reply_id,
        }
        if reply["user"] == "unknown" and not reply["text"]:
            return None
        return reply

    return None



def extract_message_fragments(node: dict) -> list[dict]:
    msg = node.get("message") or {}
    fragments = msg.get("fragments") or []

    out: list[dict] = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue

        item = {"text": fragment.get("text") or ""}
        emote = fragment.get("emote") or {}
        if isinstance(emote, dict):
            emote_id = emote.get("emoteID") or emote.get("id")
            if emote_id:
                item["emoteID"] = emote_id
            emote_name = emote.get("name")
            if emote_name:
                item["emoteName"] = emote_name

        out.append(item)

    return out


def render_message(node: dict) -> str:
    fragments = extract_message_fragments(node)
    return "".join((f.get("text") or "") for f in fragments).strip()


async def fetch_vod_meta(session: aiohttp.ClientSession, client_id: str, vod_id: str) -> VodMeta:
    from .client import gql_post_json
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

            try:
                helix_url = f"https://api.twitch.tv/helix/videos?id={vod_id}"
                helix_headers = {
                    "Client-Id": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}",
                }

                async with session.get(helix_url, headers=helix_headers) as resp:
                    data2 = await resp.json()
                    videos = data2.get("data") or []
                    if videos:
                        thumb = videos[0].get("thumbnail_url")
                        if thumb:
                            meta.thumbnail_url = thumb.replace("%{width}", "640").replace("%{height}", "360")
            except Exception:
                pass

            return meta
        except Exception:
            await asyncio.sleep(0.2 * (attempt + 1))
    return meta