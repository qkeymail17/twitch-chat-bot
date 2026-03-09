import json
from pathlib import Path

from config import TEMPLATES_DIR


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
    template_path = Path(TEMPLATES_DIR) / "viewer_template.html"
    template = template_path.read_text(encoding="utf-8")

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