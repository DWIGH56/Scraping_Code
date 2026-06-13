"""
Google Maps search scraper with human-like micro-grid scrolling.

Workflow:
1. Open Google Maps
2. Type keyword + location into the search box
3. Scroll the results panel in small micro-steps with random delays
4. Click on each listing to load the detail panel
5. Extract parsed data
"""

import asyncio
import random
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page

from config.settings import (
    GMAPS_BASE_URL,
    SCROLL_ITERATIONS,
    SCROLL_STEP_PX,
    SCROLL_DELAY_MIN,
    SCROLL_DELAY_MAX,
    SEARCH_BOX_INPUT,
    SEARCH_BOX,
    SEARCH_BUTTON,
    RESULTS_PANEL,
    RESULT_ITEMS,
    NEXT_PAGE_BUTTON,
)
from core.browser import create_browser, create_context, human_delay, close_browser
from core.parser import parse_detail_panel


async def _type_human_like(page: Page, selector: str, text: str) -> None:
    """Type text character-by-character with random inter-key delays."""
    await page.click(selector)
    await page.fill(selector, "")
    for char in text:
        await page.type(selector, char, delay=random.randint(40, 120))
        await asyncio.sleep(random.uniform(0.01, 0.04))


async def _micro_scroll(page: Page, iterations: int = SCROLL_ITERATIONS) -> None:
    """
    Perform micro-grid scrolling on the results panel.
    Each step scrolls a small distance (120 px) and waits a random delay.
    This mimics human reading behaviour and avoids bot detection.
    """
    panel = page.locator(RESULTS_PANEL)
    panel_exists = await panel.count() > 0

    for i in range(iterations):
        if panel_exists:
            await panel.evaluate(f"el => el.scrollBy(0, {SCROLL_STEP_PX})")
        else:
            await page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX})")

        # Random pause between scrolls
        await asyncio.sleep(random.uniform(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))

        # Occasionally "look" at the page by moving the mouse (human-like)
        if i % 5 == 0:
            await page.mouse.move(
                random.randint(100, 800), random.randint(100, 600), steps=5
            )


async def _collect_listing_urls(page: Page) -> list[str]:
    """
    Return all listing anchor hrefs currently visible in the results panel.
    """
    links = await page.locator(RESULT_ITEMS).all()
    urls = []
    for link in links:
        href = await link.get_attribute("href")
        if href and href.startswith("https://www.google.com/maps/place"):
            urls.append(href)
    return list(set(urls))  # deduplicate


async def scrape_google_maps(
    keyword: str,
    location: str,
    browser: Browser,
    context: BrowserContext,
    progress_callback=None,
) -> list[dict]:
    """
    Run a single search on Google Maps and return a list of lead dicts.

    Parameters
    ----------
    keyword : str      – e.g. "Plumber"
    location : str     – e.g. "Downtown Austin" (sub-district)
    browser : Browser  – Playwright Browser instance
    context : BrowserContext – isolated incognito context
    progress_callback : optional callable(status: str)

    Returns
    -------
    list[dict] with keys: name, phone, website, rating, reviews_count, address, category, plus_code
    """
    page = await context.new_page()
    leads = []

    try:
        # Set a reasonable default timeout for all operations on this page
        page.set_default_timeout(30000)

        # 1. Navigate to Google Maps
        if progress_callback:
            progress_callback(f"🌍 Navigating to Google Maps for '{keyword} {location}'")
        await page.goto(GMAPS_BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await human_delay(3, 6)

        # 2. Accept cookies if the banner appears
        try:
            accept_btn = page.locator('button:has-text("Accept all")')
            if await accept_btn.is_visible(timeout=3000):
                await accept_btn.click()
                await human_delay(1, 2)
        except Exception:
            pass

        # 3. Type the search query and location into the search box
        #    Format: "keyword in location"
        query = f"{keyword} {location}"
        if progress_callback:
            progress_callback(f"🔍 Searching: {query}")

        await _type_human_like(page, SEARCH_BOX_INPUT, query)
        await human_delay(1, 2)

        # 4. Click the search button (or press Enter)
        search_btn = page.locator(SEARCH_BUTTON)
        if await search_btn.is_visible(timeout=3000):
            await search_btn.click()
        else:
            await page.keyboard.press("Enter")

        # 5. Wait for results to load
        await page.wait_for_selector(RESULTS_PANEL, timeout=15000)
        await human_delay(3, 5)

        # 6. Micro-grid scrolling to load all available results
        if progress_callback:
            progress_callback(f"🔄 Scrolling results for '{location}'...")
        await _micro_scroll(page)

        # 7. Collect all listing URLs from the feed
        listing_urls = await _collect_listing_urls(page)
        if progress_callback:
            progress_callback(f"📋 Found {len(listing_urls)} listings in '{location}'")

        # 8. Click each listing and extract data from detail panel
        for idx, url in enumerate(listing_urls):
            try:
                if progress_callback:
                    progress_callback(
                        f"📄 Processing listing {idx + 1}/{len(listing_urls)}"
                    )

                # Navigate to the place detail page
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Extra wait for DOM to fully settle — prevents empty early rows
                await page.wait_for_timeout(1500)

                # Human-like pause after navigation before parsing
                # Google Maps may soft-block if data is scraped too quickly
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # Extract data from the detail panel
                lead = await parse_detail_panel(page)
                if lead and lead.get("name"):
                    lead["keyword"] = keyword
                    lead["location"] = location
                    leads.append(lead)
                    if progress_callback:
                        progress_callback(
                            f"  ✅ Saved: {lead['name'][:50]}"
                            f"{' — 📞 ' + lead['phone'] if lead.get('phone') else ''}"
                            f"{' — 🌐 ' + lead['website'][:40] if lead.get('website') else ''}"
                        )
                else:
                    if progress_callback:
                        progress_callback(
                            f"  ⚠️ Skipped (no data extracted) — {url[:60]}..."
                        )

            except Exception as e:
                if progress_callback:
                    progress_callback(f"⚠️ Error on listing {idx + 1}: {e}")
                continue

    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ Error scraping '{location}': {e}")
    finally:
        await page.close()

    return leads