"""
Configuration settings for the Google Maps Leads Scraper.

All configurable parameters are centralized here:
- Proxy configuration
- Randomized delay ranges
- Google Maps search base URL
- Page load / scroll / interaction timing
- Micro-targeting sub-district fallback paths
- Output paths
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
GEO_SOURCE_DIR = DATA_DIR / "geo_source"

# Ensure output directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
GEO_SOURCE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Google Maps URL
# ---------------------------------------------------------------------------
GMAPS_BASE_URL = "https://www.google.com/maps"

# ---------------------------------------------------------------------------
# Proxy Configuration
# ---------------------------------------------------------------------------
# Set to an empty list to disable proxies (direct connection).
# Each entry should be a dict: {"server": "http://user:pass@host:port"}
# Or a plain string: "http://user:pass@host:port"
PROXIES: list[dict | str] = [
    # Example:
    # {"server": "http://user:pass@1.2.3.4:8080"},
]

# Rotate proxy per N searches (0 = never rotate)
PROXY_ROTATION_INTERVAL = 0

# ---------------------------------------------------------------------------
# Request / Interaction Delays (in seconds)
# ---------------------------------------------------------------------------
# Random delay range applied before each page interaction
MIN_DELAY = 2.0
MAX_DELAY = 5.0

# Delay after page navigation / scroll step (simulates human reading)
SCROLL_DELAY_MIN = 0.8
SCROLL_DELAY_MAX = 2.2

# Delay after clicking a listing
CLICK_DELAY_MIN = 1.5
CLICK_DELAY_MAX = 3.5

# ---------------------------------------------------------------------------
# Browser Viewport
# ---------------------------------------------------------------------------
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080

# ---------------------------------------------------------------------------
# Scrolling behaviour (micro-grid scrolling)
# ---------------------------------------------------------------------------
# Number of micro-scrolls per search
SCROLL_ITERATIONS = 40
# Pixels per micro-scroll step
SCROLL_STEP_PX = 120

# ---------------------------------------------------------------------------
# Anti-detection tweaks
# ---------------------------------------------------------------------------
# Whether to run in headful mode (visible browser) – HIGHLY recommended
HEADLESS = False

# Locale for the browser
LOCALE = "en-US"
TIMEZONE_ID = "America/New_York"

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# DOM selectors for Google Maps (used by core.scraper and core.parser)
# ---------------------------------------------------------------------------
# These are CSS selector strings for the Google Maps DOM.
# Centralised here to avoid circular imports between core modules.
SEARCH_BOX_INPUT = 'input[name="q"]'
SEARCH_BOX = "#searchboxinput"
SEARCH_BUTTON = "#searchbox-searchbutton"
RESULTS_PANEL = 'div[role="feed"]'
RESULT_ITEMS = 'a[href*="/maps/place/"]'
NEXT_PAGE_BUTTON = 'button[aria-label*="Next page"]'

# ---------------------------------------------------------------------------
# Search & micro-targeting
# ---------------------------------------------------------------------------
# Google Maps displays at most ~120 results on a search.
# To get more leads we split a big city into smaller sub-districts.
ENABLE_MICRO_TARGETING = True

# If a geo source JSON file exists with sub-districts for a location,
# the scraper will iterate through them automatically.
# File format: {"location_name": ["Sub-district 1", "Sub-district 2", ...]}
GEO_SOURCE_FILE = GEO_SOURCE_DIR / "sub_districts.json"

# ---------------------------------------------------------------------------
# CSV / PDF / XLSX output
# ---------------------------------------------------------------------------
DEFAULT_CSV_NAME = "gmaps_leads.csv"
DEFAULT_PDF_NAME = "gmaps_leads.pdf"
DEFAULT_XLSX_NAME = "gmaps_leads.xlsx"

# PDF watermark string
WATERMARK_TEXT = "CONFIDENTIAL - PROPRIETARY DATA"
WATERMARK_OPACITY = 0.12  # 0.0 - 1.0

# ---------------------------------------------------------------------------
# Database (SQLite / PostgreSQL)
# ---------------------------------------------------------------------------
# "sqlite" or "postgresql"
DB_ENGINE = "sqlite"
SQLITE_DB_PATH = str(BASE_DIR / "data" / "leads.db")
POSTGRES_DSN = "postgresql://user:password@localhost:5432/gmaps_leads"

# ---------------------------------------------------------------------------
# Helper: load sub-districts from JSON
# ---------------------------------------------------------------------------
def load_sub_districts(location: str) -> list[str]:
    """Return a list of sub-districts for *location* from the geo-source file,
    falling back to the original location if none are found."""
    if not GEO_SOURCE_FILE.exists():
        return [location]

    with open(GEO_SOURCE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Case-insensitive key lookup
    for key, districts in data.items():
        if key.lower() == location.lower():
            return districts if isinstance(districts, list) else [location]

    return [location]