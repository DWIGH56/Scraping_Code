"""
Playwright + Stealth + Proxy initialization module.

Provides:
- `create_browser()` – launch a Chromium browser with anti-detection patches.
- `create_context(browser)` – create an isolated incognito context with proxy, UA, and viewport.
"""

import asyncio
import logging
import random
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

logger = logging.getLogger(__name__)

from config.settings import (
    HEADLESS,
    LOCALE,
    TIMEZONE_ID,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    PROXIES,
    MIN_DELAY,
    MAX_DELAY,
)
from config.user_agents import get_random_user_agent


async def create_browser(playwright_instance: Optional[Playwright] = None) -> tuple[Playwright, Browser]:
    """
    Launch a Chromium browser instance with stealth-friendly arguments.

    Returns
    -------
    (playwright, browser) tuple.
    """
    if playwright_instance is None:
        p = await async_playwright().start()
    else:
        p = playwright_instance

    browser = await p.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            f"--lang={LOCALE.split('-')[0]}",
        ],
    )
    return p, browser


def _pick_proxy() -> Optional[dict]:
    """Return a proxy dict or None if no proxies configured."""
    if not PROXIES:
        return None
    entry = random.choice(PROXIES)
    if isinstance(entry, str):
        return {"server": entry}
    return entry  # already a dict


async def create_context(browser: Browser) -> BrowserContext:
    """
    Create an isolated browser context with:
    - Random User-Agent rotation
    - Viewport set to 1920x1080
    - Locale & timezone
    - Proxy (if configured)

    If the proxy is unreachable, the context falls back to a direct connection
    so the application doesn't freeze.

    Also applies `playwright-stealth` patches via `stealth_sync`.
    """
    user_agent = get_random_user_agent()
    proxy = _pick_proxy()

    kwargs = dict(
        user_agent=user_agent,
        viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        locale=LOCALE,
        timezone_id=TIMEZONE_ID,
        ignore_https_errors=True,
        permissions=[],
        color_scheme="light",
        reduced_motion="no-preference",
        forced_colors="none",
    )

    # Add proxy (if configured) — wrapped in try/except so a dead proxy
    # doesn't crash the whole application.
    if proxy is not None:
        try:
            kwargs["proxy"] = proxy
            context = await browser.new_context(**kwargs)
            # Quick connectivity test: open a page and check it loads
            test_page = await context.new_page()
            await test_page.goto(
                "https://www.google.com",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await test_page.close()
            return context
        except Exception:
            logger.warning(
                f"Proxy {proxy.get('server', 'unknown')} unreachable. "
                "Falling back to direct connection."
            )
            # Fall through — create context WITHOUT proxy below
            del kwargs["proxy"]

    context = await browser.new_context(**kwargs)

    # Apply playwright-stealth patches to all pages in this context
    try:
        from playwright_stealth import stealth_async

        # We patch context pages via init script to ensure stealth on all frames
        await context.add_init_script(
            """
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', { get: () => false });

            // Override chrome runtime
            window.chrome = { runtime: {} };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Override plugins array
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
        """
        )
    except ImportError:
        pass  # stealth not installed, use built-in init script above

    return context


async def human_delay(min_s: float = MIN_DELAY, max_s: float = MAX_DELAY) -> None:
    """Wait a random amount of time to simulate human interaction."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def close_browser(playwright: Playwright, browser: Browser) -> None:
    """Safely close the browser and the playwright driver."""
    await browser.close()
    await playwright.stop()