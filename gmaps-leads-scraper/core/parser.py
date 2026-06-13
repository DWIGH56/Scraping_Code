"""
HTML parser for Google Maps listing detail pages.

Extracts structured lead data using robust data-attribute selectors and
text regex fallbacks — avoids brittle CSS class names that Google Maps
frequently changes.
"""

import re
import logging
from typing import Optional

from playwright.async_api import Page

from config.settings import RESULT_ITEMS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Smart URL Distributor
# ---------------------------------------------------------------------------
# When Google Maps gives us a URL from the website field, analyse it first:
#   - instagram.com      → put in Instagram, Website stays "-"
#   - facebook.com/fb.com → put in Facebook, Website stays "-"
#   - tiktok.com         → put in TikTok, Website stays "-"
#   - wa.me / api.whatsapp.com → extract phone, Website stays "-"
#   - real domain (.com, .id, .net, etc.) → put in Website

_SOCIAL_DOMAINS = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "tiktok.com": "tiktok",
}

_WHATSAPP_PATTERNS = [
    r"wa\.me/(\d+)",
    r"api\.whatsapp\.com/send/?\?phone=(\d+)",
]

_REAL_TLDS = {".com", ".id", ".net", ".org", ".co.id", ".co", ".io", ".app",
               ".me", ".info", ".biz", ".my", ".sg", ".hk", ".th", ".ph"}


def distribute_website_url(raw_url: Optional[str]) -> dict:
    """
    Distribute a raw URL from Google Maps into the appropriate field.

    Returns a dict with keys: website, instagram, facebook, tiktok, phone
    """
    result = {
        "website": None,
        "instagram": None,
        "facebook": None,
        "tiktok": None,
        "phone": None,
    }

    if not raw_url or not raw_url.strip():
        return result

    url_lower = raw_url.strip().lower()

    # 1. Check WhatsApp patterns first — extract phone
    for pattern in _WHATSAPP_PATTERNS:
        match = re.search(pattern, url_lower)
        if match:
            phone_digits = match.group(1)
            # Format as Indonesian number if starts with 62
            if phone_digits.startswith("62"):
                result["phone"] = "+" + phone_digits
            elif phone_digits.startswith("0"):
                result["phone"] = "+62" + phone_digits[1:]
            else:
                result["phone"] = "+62" + phone_digits
            return result

    # 2. Check social media domains
    for domain, field in _SOCIAL_DOMAINS.items():
        if domain in url_lower:
            # Ensure it's a profile, not just the homepage
            parts = url_lower.split(domain, 1)
            if len(parts) > 1 and parts[1] and parts[1] not in ("/", "", "?"):
                result[field] = raw_url.strip()
                return result
            # If it's just the homepage, treat as website fallback
            break

    # 3. Check if it looks like a real domain
    try:
        from urllib.parse import urlparse
        parsed = urlparse(raw_url.strip())
        domain = parsed.netloc or parsed.path
        # Check TLD
        for tld in _REAL_TLDS:
            if domain.endswith(tld) or domain.endswith("." + tld):
                result["website"] = raw_url.strip()
                return result
    except Exception:
        pass

    # 4. Fallback — save as website
    result["website"] = raw_url.strip()
    return result

# ---------------------------------------------------------------------------
# Robust selectors based on data-item-id, data-tooltip, and aria-label
# Google Maps uses these attributes consistently across versions.
# ---------------------------------------------------------------------------

# Name — the business title is always the first / only <h1> on the detail page
TITLE_SELECTOR = "h1"

# Address — button with data-item-id containing "address"
ADDRESS_SELECTOR = 'button[data-item-id*="address"]'

# Phone — two reliable patterns:
#   - data-item-id="phone:tel:+1234567890"
#   - data-tooltip="Copy phone number" (English)
PHONE_SELECTOR = (
    'a[data-item-id*="phone:tel:"], '
    '[data-tooltip*="phone" i], '
    '[data-tooltip*="Copy phone number" i], '
    'button[data-item-id*="phone"]'
)

# Website — anchor with data-item-id="authority" or data-tooltip containing "website"
WEBSITE_SELECTOR = (
    'a[data-item-id="authority"], '
    'a[data-tooltip*="website" i], '
    'a[data-tooltip*="Open website" i]'
)

# Plus code
PLUS_CODE_SELECTOR = 'button[data-item-id*="oloc"]'

# Opening hours
HOURS_SELECTOR = 'div[class*="hours"]'


def _extract_rating_from_aria(aria_label: str) -> Optional[float]:
    """Parse a float rating from an aria-label like '4.2 stars' or '5.0 star rating'."""
    match = re.search(r"(\d+\.?\d*)", aria_label)
    return float(match.group(1)) if match else None


def _extract_reviews_from_aria(aria_label: str) -> Optional[int]:
    """Parse an integer review count from text like '2,345 reviews'."""
    numbers = re.findall(r"[\d,]+", aria_label)
    if numbers:
        return int(numbers[0].replace(",", ""))
    return None


async def parse_detail_panel(page: Page) -> Optional[dict]:
    """
    Extract lead information from the Google Maps place detail page.

    Uses stable data-attribute selectors with text/regex fallbacks so that
    minor DOM updates by Google Maps do not break extraction.

    Returns a dict with keys:
        name, phone, website, rating, reviews_count, address, category,
        plus_code, hours
    Returns None if the page isn't a valid place page (name missing).
    """
    lead = {
        "name": None,
        "phone": None,
        "website": None,
        "instagram": None,
        "facebook": None,
        "tiktok": None,
        "rating": None,
        "reviews_count": None,
        "address": None,
        "plus_code": None,
        "hours": None,
    }

    try:
        # Wait for the detail panel to render fully
        await page.wait_for_timeout(2500)

        # --- Name (always the only <h1> on Google Maps place pages) ---
        try:
            h1 = page.locator("h1").first
            if await h1.is_visible(timeout=3000):
                lead["name"] = (await h1.inner_text()).strip()
        except Exception:
            pass

        if not lead["name"]:
            try:
                # Fallback: page <title> tag
                title = await page.title()
                # Google Maps titles look like: "Business Name - Google Maps"
                if " - Google Maps" in title:
                    lead["name"] = title.replace(" - Google Maps", "").strip()
                else:
                    lead["name"] = title.strip()
            except Exception:
                pass

        # --- Address ---
        try:
            addr = page.locator(ADDRESS_SELECTOR).first
            if await addr.is_visible(timeout=2000):
                # Try aria-label first
                raw = await addr.get_attribute("aria-label")
                if raw and "Address:" in raw:
                    lead["address"] = raw.replace("Address:", "").strip()
                else:
                    # Fallback to button text
                    text = await addr.inner_text()
                    if text.strip():
                        lead["address"] = text.strip()
        except Exception:
            pass

        # --- Phone ---
        try:
            phone_el = page.locator(PHONE_SELECTOR).first
            if await phone_el.is_visible(timeout=2000):
                # Try aria-label
                raw = await phone_el.get_attribute("aria-label")
                if raw:
                    lead["phone"] = raw.replace("Phone:", "").strip()
                else:
                    text = await phone_el.inner_text()
                    # Remove common UI prefixes
                    cleaned = re.sub(r"^(Phone|Tel|Telephone)[:\s]*", "", text, flags=re.IGNORECASE).strip()
                    if cleaned:
                        lead["phone"] = cleaned
        except Exception:
            pass

        # --- Website (with Smart URL Distributor) ---
        try:
            web_el = page.locator(WEBSITE_SELECTOR).first
            if await web_el.is_visible(timeout=2000):
                href = await web_el.get_attribute("href")
                if href and href.startswith("http"):
                    # Run through Smart URL Distributor
                    distributed = distribute_website_url(href.strip())
                    if distributed["website"]:
                        lead["website"] = distributed["website"]
                    if distributed["instagram"]:
                        lead["instagram"] = distributed["instagram"]
                    if distributed["facebook"]:
                        lead["facebook"] = distributed["facebook"]
                    if distributed["tiktok"]:
                        lead["tiktok"] = distributed["tiktok"]
                    if distributed["phone"]:
                        lead["phone"] = distributed["phone"]
        except Exception:
            pass

        # --- Rating & Reviews Count (combined extraction) ---
        # Google Maps places the rating + review count together in one aria-label
        # on a span/div near the title: e.g. "4,5 bintang 82 ulasan" or "4.5 stars 82 reviews"
        rating_found = False
        try:
            # Strategy 1: aria-label containing "bintang", "stars", "star", "rating"
            rating_el = page.locator(
                '[aria-label*="bintang" i], '
                '[aria-label*="stars" i], '
                '[aria-label*="star" i], '
                '[aria-label*="rating" i]'
            ).first
            if await rating_el.is_visible(timeout=2000):
                aria = await rating_el.get_attribute("aria-label")
                if aria:
                    # Polish / Indonesian: "4,5 bintang 82 ulasan"
                    # English: "4.5 stars 82 reviews"
                    # Extract ALL numbers from the aria-label
                    parts = re.findall(r"[\d,]+\.?[\d,]*", aria.replace(" ", ""))
                    numbers_clean = []
                    for p in parts:
                        # Convert comma-as-decimal to dot: "4,5" → "4.5"
                        cleaned = p.replace(",", ".")
                        try:
                            val = float(cleaned)
                            numbers_clean.append(val)
                        except ValueError:
                            pass

                    if len(numbers_clean) >= 1:
                        lead["rating"] = numbers_clean[0]
                        rating_found = True
                    if len(numbers_clean) >= 2:
                        lead["reviews_count"] = int(numbers_clean[1])
                    elif len(numbers_clean) == 1:
                        # Single number found — might be rating only; try secondary selector for reviews
                        pass
        except Exception:
            pass

        # Strategy 2: If rating not found by aria-label, look for visible text pattern
        # "4.5 (82)" near the title area
        if not rating_found:
            try:
                # Get all text content from the detail header area
                header_area = page.locator(
                    'div[class*="header"], div[class*="title"], div[class*="info"]'
                ).first
                header_text = ""
                if await header_area.is_visible(timeout=1000):
                    header_text = await header_area.inner_text()
                else:
                    # Fallback: get body text near top
                    header_text = await page.locator("body").inner_text()
                    header_text = header_text[:2000]

                # Pattern: float number followed optionally by parenthesized number
                # e.g. "4.5 (82)" or "4,2 (45 ulasan)"
                combined = re.search(
                    r"(\d+[.,]\d+)\s*[\(\[]?\s*(\d+[\d,]*)\s*[\)\]]?",
                    header_text
                )
                if combined:
                    raw_rating = combined.group(1).replace(",", ".")
                    raw_reviews = combined.group(2).replace(",", "")
                    try:
                        lead["rating"] = float(raw_rating)
                        rating_found = True
                    except ValueError:
                        pass
                    try:
                        lead["reviews_count"] = int(raw_reviews)
                    except ValueError:
                        pass

            except Exception:
                pass

        # Strategy 3: If still not found, debug-log the HTML of the header area
        if not rating_found:
            try:
                # Get a snippet of the page HTML around where rating should be
                snippet = await page.locator("body").inner_html()
                # Focus on the first ~3000 chars to see the header structure
                debug_html = snippet[:3000]
                logger.warning(
                    "Rating/Review extraction failed. "
                    "Page title: %s | Header HTML snippet (first 3000 chars):\n%s",
                    await page.title(),
                    debug_html,
                )
            except Exception:
                pass

        # --- Plus Code ---
        try:
            plus_el = page.locator(PLUS_CODE_SELECTOR).first
            if await plus_el.is_visible(timeout=2000):
                raw = await plus_el.get_attribute("aria-label")
                if raw:
                    lead["plus_code"] = raw.replace("Plus code:", "").strip()
        except Exception:
            pass

        # --- Hours ---
        try:
            hours_el = page.locator(HOURS_SELECTOR).first
            if await hours_el.is_visible(timeout=2000):
                lead["hours"] = (await hours_el.inner_text()).strip()
        except Exception:
            pass

        # Log a warning if name is still empty so the user knows why
        if not lead["name"]:
            logger.warning(
                "parse_detail_panel: could not extract business name. "
                "Page title was: %s", await page.title()
            )

        return lead if lead.get("name") else None

    except Exception as exc:
        logger.debug("parse_detail_panel exception: %s", exc)
        return None


async def parse_listing_card(page: Page, card_index: int) -> Optional[dict]:
    """
    Parse a single listing card from the results feed (before clicking).
    This is useful if you don't want to navigate to each detail page.

    Returns a dict with at minimum: name, rating, reviews_count.
    """
    try:
        cards = page.locator(RESULT_ITEMS)
        card = cards.nth(card_index)

        aria_label = (await card.get_attribute("aria-label")) or ""
        name = aria_label.split("·")[0].strip() if "·" in aria_label else aria_label
        rating = None
        reviews = None

        if aria_label:
            match = re.search(r"(\d+\.?\d*)\s*★", aria_label)
            if match:
                rating = float(match.group(1))
            rev_match = re.search(r"(\d[\d,]*) reviews?", aria_label)
            if rev_match:
                reviews = int(rev_match.group(1).replace(",", ""))

        return {
            "name": name,
            "rating": rating,
            "reviews_count": reviews,
        }
    except Exception:
        return None