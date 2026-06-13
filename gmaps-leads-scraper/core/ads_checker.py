"""
Background module to check if a business website has Google Ads / Facebook Pixel.

Uses the synchronous `requests` library to fetch the page HTML and scans for
ad-related scripts via regex patterns. Async-wrapped with `asyncio.to_thread`
so it integrates cleanly with the async pipeline without httpx.
"""

import asyncio
import logging
import re
from typing import Optional

import requests
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# ---- Constants -----------------------------------------------------------
REQUEST_TIMEOUT = 15  # seconds

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Patterns to detect ad platforms
GOOGLE_ADS_PATTERNS = [
    r"googlesyndication\.com",
    r"googleads\.g\.doubleclick\.net",
    r"google_ad_client",
    r"adsbygoogle",
    r"google_adsense",
    r"gpt\.defineSlot",            # Google Publisher Tag
    r"googletag\.cmd",
]

FACEBOOK_PIXEL_PATTERNS = [
    r"facebook\.com/tr\b",
    r"fbq\s*\(['\"]track['\"]",
    r"connect\.facebook\.net",
    r"fb_pixel",
    r"\.fbq\b",
]


# ---- Synchronous worker (runs in a thread via asyncio) -------------------
def _sync_check_website(website_url: str) -> dict:
    """
    Synchronous HTTP GET that scans HTML for ad scripts.
    This runs inside `asyncio.to_thread` to avoid blocking the event loop.
    """
    result = {
        "url": website_url,
        "has_google_ads": False,
        "has_facebook_pixel": False,
        "error": None,
    }

    if not website_url or not website_url.startswith("http"):
        result["error"] = "Invalid URL"
        return result

    try:
        response = requests.get(
            website_url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            verify=False,       # ignore SSL cert errors
        )

        if response.status_code != 200:
            result["error"] = f"HTTP {response.status_code}"
            return result

        html = response.text

        # Check Google Ads
        for pattern in GOOGLE_ADS_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_google_ads"] = True
                break

        # Check Facebook Pixel
        for pattern in FACEBOOK_PIXEL_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_facebook_pixel"] = True
                break

    except requests.ConnectionError:
        result["error"] = "ConnectionError"
    except requests.Timeout:
        result["error"] = "Timeout"
    except requests.RequestException as e:
        result["error"] = str(e)
    except Exception as e:
        result["error"] = str(e)

    return result


# ---- Public async API ---------------------------------------------------
async def check_website_for_ads(website_url: str) -> dict:
    """
    Check a website URL for the presence of Google Ads and Facebook Pixel
    scripts by fetching the page HTML and scanning with regex patterns.

    Uses `asyncio.to_thread` to run the synchronous ``requests.get`` call
    without blocking the asyncio event loop.

    Returns
    -------
    dict with keys:
        url : str
        has_google_ads : bool
        has_facebook_pixel : bool
        error : Optional[str]
    """
    return await asyncio.to_thread(_sync_check_website, website_url)


async def check_website_via_page(page: Page, website_url: str) -> dict:
    """
    Alternative method: loads the website in a Playwright page and scans for
    ad scripts. More reliable for JS-heavy sites but significantly slower.

    Returns same dict format as `check_website_for_ads`.
    """
    result = {
        "url": website_url,
        "has_google_ads": False,
        "has_facebook_pixel": False,
        "error": None,
    }

    if not website_url:
        result["error"] = "No URL"
        return result

    try:
        await page.goto(website_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # Get the full page HTML (after JS execution)
        html = await page.content()

        # Check Google Ads
        for pattern in GOOGLE_ADS_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_google_ads"] = True
                break

        # Check Facebook Pixel
        for pattern in FACEBOOK_PIXEL_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                result["has_facebook_pixel"] = True
                break

    except Exception as e:
        result["error"] = str(e)

    return result