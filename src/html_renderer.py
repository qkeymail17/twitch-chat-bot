import json
from pathlib import Path


def render_fragments(fragments: list) -> str:
    if not fragments:
        return ""

    parts = []

    for f in fragments:
        text = f.get("text", "")
        emote = f.get("emote")

        if emote and emote.get("emoteID"):
            emote_id = emote["emoteID"]
            url = f"https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/3.0"

            parts.append(f'<img src="{url}" alt="{text}" class="emote">')
        else:
            parts.append(text)

    return "".join(parts)


def render_viewer_html(
    chat_rows: list[dict],
    title: str,
    channel: str,
    vod_url: str,
    created_at: str | None = None,
    mode: str = "online",
    channel_id: str | None = None,
    local_emotes: dict | None = None,
    cdn_emotes: dict | None = None,
) -> str:
    BASE_DIR = Path(__file__).resolve().parent
    template_path = BASE_DIR / "viewer_template.html"
    template = template_path.read_text(encoding="utf-8")

    for row in chat_rows:
        fragments = row.get("fragments")
        if fragments:
            row["text"] = render_fragments(fragments)

    payload = {
        "meta": {
            "title": title,
            "channel": channel,
            "vod_url": vod_url,
            "created_at": created_at,
            "mode": mode,
            "channel_id": channel_id,
            "local_emotes": local_emotes or {},
            "cdn_emotes": cdn_emotes or {},
        },
        "rows": chat_rows,
    }

    data_json = json.dumps(payload, ensure_ascii=False).replace("</script>", "<\\/script>")
    return template.replace("{{CHAT_DATA_JSON}}", data_json)