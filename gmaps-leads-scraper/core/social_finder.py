"""
Social Media & Email Finder Module.

Scans a business website's HTML source (ONE request per lead) for:
- Instagram profile URL
- Facebook profile URL
- TikTok profile URL
- Email address (Gmail or business domain email)

Uses requests + regex with a 7-second timeout per website.
"""

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 7

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
INSTAGRAM_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+/?',
    re.IGNORECASE,
)

FACEBOOK_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:facebook\.com|fb\.com)/[a-zA-Z0-9.]+(?:/)?'
    r'(?:\?.*)?$',
    re.IGNORECASE,
)

TIKTOK_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.]+/?',
    re.IGNORECASE,
)

# Bulletproof email regex — strictly matches valid email addresses
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
)

# File extensions to filter out (false positives)
_EMAIL_BLACKLIST_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg",
                               ".webp", ".ico", ".css", ".js", ".json",
                               ".xml", ".woff", ".woff2", ".ttf", ".eot"}

# Common email prefixes that indicate a valid contact email
_VALID_EMAIL_PREFIXES = {"info", "contact", "hello", "support", "sales",
                          "admin", "mail", "business", "inquiry", "enquiry",
                          "customerservice", "cs", "help", "care",
                          "team", "office", "reservations", "booking"}


def _clean_url(url: str) -> str:
    """Strip trailing slashes, query strings from social URLs."""
    url = url.rstrip("/")
    if "?" in url:
        url = url.split("?")[0]
    return url


def _is_valid_email(email: str) -> bool:
    """
    Validate that an extracted string is a real email address,
    not an image file path or other false positive.
    """
    # Must contain exactly one @
    if email.count("@") != 1:
        return False

    # Check extension blacklist
    ext = "." + email.split(".")[-1].lower()
    if f".{ext}" in _EMAIL_BLACKLIST_EXTENSIONS or ext in _EMAIL_BLACKLIST_EXTENSIONS:
        return False

    # Must have a domain with at least one dot
    if "." not in email.split("@")[1]:
        return False

    return True


def _prioritize_email(emails: list[str]) -> Optional[str]:
    """
    From a list of found emails, pick the best one.
    Priority order:
    1. Gmail addresses (user@gmail.com)
    2. Business emails with common prefixes (info@domain.com)
    3. Any other valid email
    """
    gmail_candidates = []
    prefix_candidates = []
    other_candidates = []

    for email in emails:
        if not _is_valid_email(email):
            continue
        lower = email.lower()
        if lower.endswith("@gmail.com"):
            gmail_candidates.append(email)
        elif lower.split("@")[0] in _VALID_EMAIL_PREFIXES:
            prefix_candidates.append(email)
        else:
            other_candidates.append(email)

    if gmail_candidates:
        return gmail_candidates[0]
    if prefix_candidates:
        return prefix_candidates[0]
    if other_candidates:
        return other_candidates[0]
    return None


def _find_email_in_html(html: str) -> Optional[str]:
    """
    Scan HTML text for email addresses, filter false positives,
    and return the best candidate.
    """
    matches = EMAIL_PATTERN.findall(html)
    unique = list(dict.fromkeys(matches))  # preserve order, deduplicate
    return _prioritize_email(unique)


def enrich_website_data(website_url: str) -> dict[str, Optional[str]]:
    """
    Scan the given website URL for social media links AND email addresses.
    Makes a SINGLE HTTP request per lead for max efficiency.

    Parameters
    ----------
    website_url : str – the business website

    Returns
    -------
    dict with keys: instagram, facebook, tiktok, email
    Each value is the discovered URL/email string, or None if not found.
    """
    result: dict[str, Optional[str]] = {
        "instagram": None,
        "facebook": None,
        "tiktok": None,
        "email": None,
    }

    if not website_url or not website_url.startswith("http"):
        return result

    html = ""
    try:
        response = requests.get(
            website_url,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            verify=False,
        )
        if response.status_code == 200:
            html = response.text
    except requests.ConnectionError:
        logger.debug(f"Enricher: ConnectionError for {website_url}")
        return result
    except requests.Timeout:
        logger.debug(f"Enricher: Timeout for {website_url}")
        return result
    except Exception as e:
        logger.debug(f"Enricher: {e} for {website_url}")
        return result

    if not html:
        return result

    # --- Instagram ---
    insta_matches = INSTAGRAM_PATTERN.findall(html)
    if insta_matches:
        clean = _clean_url(insta_matches[0])
        if clean.rstrip("/") not in ("https://instagram.com", "http://instagram.com",
                                      "https://www.instagram.com", "http://www.instagram.com"):
            result["instagram"] = clean

    # --- Facebook ---
    fb_matches = FACEBOOK_PATTERN.findall(html)
    if fb_matches:
        clean = _clean_url(fb_matches[0])
        if clean.rstrip("/") not in ("https://facebook.com", "http://facebook.com",
                                      "https://www.facebook.com", "http://www.facebook.com",
                                      "https://fb.com", "http://fb.com"):
            result["facebook"] = clean

    # --- TikTok ---
    tt_matches = TIKTOK_PATTERN.findall(html)
    if tt_matches:
        clean = _clean_url(tt_matches[0])
        result["tiktok"] = clean

    # --- Email ---
    result["email"] = _find_email_in_html(html)

    return result