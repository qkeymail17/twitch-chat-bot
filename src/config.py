import os
import re

# --- Env ---
ENV_TOKEN = "TELEGRAM_BOT_TOKEN_TWITCH"
ENV_TWITCH_CLIENT_ID = "TWITCH_GQL_CLIENT_ID"

# --- Twitch API (OAuth) ---
TWITCH_CLIENT_ID = "uqdfspoy5ysdly7l52pfrcqj0nvt4a"
TWITCH_ACCESS_TOKEN = "9t6iqnf2rn43kce6twv2rhbq23k1dl"

# --- Twitch GraphQL (unofficial) ---
GQL_ENDPOINT = "https://gql.twitch.tv/gql"
VIDEO_COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"
DEFAULT_CLIENT_ID = "kd1unb4b3q4t58fwlpcbzcbnm76a8fp"

# Strict URL format
VOD_URL_RE = re.compile(r"^https://www\.twitch\.tv/(?:videos/|[^/]+/v/)(\d+)")

# Output
OUT_DIR = "../_out"
TEMPLATES_DIR = "templates"

# Progress
PROGRESS_INTERVAL = 3.0

# Pending selection TTL
PENDING_TTL_SECONDS = 180

# DB file
DB_PATH = os.getenv("TCD_DB_PATH", "vod_history.db")

# Cache TTL in DB (seconds) — can prune old cache later if you want
CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

# GQL tuning
FETCH_DELAY_BASE = 0.05
FETCH_DELAY_MAX = 1.5
GQL_MAX_RETRIES = 6
GQL_TIMEOUT_S = 25

# Logging
LOG_LEVEL = os.getenv("TCD_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Public HTML links
PUBLIC_HTML_DIR = "/var/www/html/public_html"
PUBLIC_BASE_URL = "http://89.167.77.210"
PUBLIC_HTML_URL_PREFIX = "/public_html"