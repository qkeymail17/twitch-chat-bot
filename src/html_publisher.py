import os
import uuid

from config import PUBLIC_HTML_DIR, PUBLIC_BASE_URL, PUBLIC_HTML_URL_PREFIX


def publish_html(html_text: str) -> str:
    os.makedirs(PUBLIC_HTML_DIR, exist_ok=True)

    filename = f"chat_{uuid.uuid4().hex}.html"
    filepath = os.path.join(PUBLIC_HTML_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_text)

    return f"{PUBLIC_BASE_URL}{PUBLIC_HTML_URL_PREFIX}/{filename}"