import time
from typing import Optional
from telegram.ext import ContextTypes
from config import VOD_URL_RE, PENDING_TTL_SECONDS


def extract_vod_id_strict(url: str) -> Optional[str]:
    m = VOD_URL_RE.match(url.strip())
    return m.group(1) if m else None


def is_busy(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("vod_busy"))


def set_busy(context: ContextTypes.DEFAULT_TYPE, v: bool):
    context.user_data["vod_busy"] = v


def set_pending(context: ContextTypes.DEFAULT_TYPE, vod_url: str, vod_id: str):
    context.user_data["vod_pending"] = {
        "vod_url": vod_url,
        "vod_id": vod_id,
        "created_at": time.time(),
    }


def get_pending(context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    return context.user_data.get("vod_pending")


def clear_pending(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("vod_pending", None)


def pending_expired(p: dict) -> bool:
    return (time.time() - float(p.get("created_at") or 0)) > PENDING_TTL_SECONDS