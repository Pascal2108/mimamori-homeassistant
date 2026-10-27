"""Constants of the mimamori integration."""
import re
from datetime import timedelta

DOMAIN = "mimamori"

# Read-only tokens from mimamori's Settings → API tokens
TOKEN_RE = re.compile(r"^mmr_[A-Za-z0-9_-]{43}$")
API_PATH = "/api/v1/summary"
API_VERSION = 1

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MIN_SCAN_SECONDS = 30
MAX_SCAN_SECONDS = 3600
CONF_SCAN_SECONDS = "scan_seconds"

REQUEST_TIMEOUT = 20  # seconds
MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # far more than any real answer

# Values of the API (docs/api.md in the mimamori repository)
SEVERITIES = ["none", "low", "medium", "critical"]
DRIVE_STATES = ["healthy", "watch", "failing", "missing"]
