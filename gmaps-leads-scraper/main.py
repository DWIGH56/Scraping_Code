"""
Main orchestrator for the Google Maps Leads Scraper.

Workflow:
1. Load sub-districts from geo_source (micro-targeting)
2. For each sub-district, launch Playwright browser with stealth + proxy
3. Scrape Google Maps listings
4. Check websites for Google Ads / FB Pixel (optional)
5. Save results to CSV, PDF (watermarked), and SQLite database
"""

import asyncio
import csv
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Callable, Optional

# Ensure project root is on path for direct `python main.py` execution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    OUTPUT_DIR,
    DEFAULT_CSV_NAME,
    DEFAULT_PDF_NAME,
    DEFAULT_XLSX_NAME,
    ENABLE_MICRO_TARGETING,
    load_sub_districts,
)
from core.browser import create_browser, create_context, human_delay, close_browser
from core.scraper import scrape_google_maps
from core.ads_checker import check_website_for_ads
from utils.database import init_db, save_leads
from utils.pdf_generator import generate_pdf
from utils.data_cleaner import clean_leads, export_to_xlsx, standardize_phone
from core.social_finder import enrich_website_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


async def run_scraper(
    keyword: str,
    location: str,
    enable_ads_check: bool = True,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[dict]:
    """
    Main scraping pipeline.

    Parameters
    ----------
    keyword : str
    location : str
    enable_ads_check : bool – if True, check each website for Google Ads / FB Pixel
    progress_callback : callable(status: str) – for real-time UI updates
    cancel_event : threading.Event – set by UI to cancel the operation

    Returns
    -------
    list[dict] – all scraped leads merged across sub-districts.
    """
    all_leads: list[dict] = []

    # 1. Multi-keyword splitting (e.g. "laundry, tempat cuci baju")
    keywords = [kw.strip() for kw in keyword.split(",") if kw.strip()]
    if not keywords:
        keywords = [keyword]

    # 2. Comma-separated multi-location input (e.g. "pasar minggu, pancoran, tebet")
    #    Splits first, then each piece goes through micro-targeting below.
    raw_parts = [part.strip() for part in location.split(",") if part.strip()]
    sub_districts: list[str] = []
    for part in raw_parts:
        if ENABLE_MICRO_TARGETING:
            districts = load_sub_districts(part)
            sub_districts.extend(districts)
        else:
            sub_districts.append(part)

    if progress_callback:
        progress_callback(
            f"🔑 {len(keywords)} keyword(s): {', '.join(keywords)} | "
            f"📍 {len(sub_districts)} sub-district(s): {', '.join(sub_districts)}"
        )

    # Check for cancellation before launch
    if cancel_event and cancel_event.is_set():
        return []

    # Launch the browser ONCE and reuse it across all sub-districts
    p, browser = await create_browser()

    try:
        for idx, sub_location in enumerate(sub_districts):
            # Check cancellation
            if cancel_event and cancel_event.is_set():
                if progress_callback:
                    progress_callback("⛔ Operation cancelled.")
                break

            if progress_callback:
                progress_callback(
                    f"\n{'='*50}\n"
                    f"📍 Sub-district {idx + 1}/{len(sub_districts)}: '{sub_location}'\n"
                    f"{'='*50}"
                )

            # Create a fresh context for each sub-district (new UA, new fingerprint)
            context = await create_context(browser)

            try:
                # Scrape Google Maps for this sub-district
                leads = await scrape_google_maps(
                    keyword=keyword,
                    location=sub_location,
                    browser=browser,
                    context=context,
                    progress_callback=progress_callback,
                )

                if progress_callback:
                    progress_callback(
                        f"📊 Got {len(leads)} leads from '{sub_location}'"
                    )

                # Optionally check websites for ads
                if enable_ads_check and leads:
                    if progress_callback:
                        progress_callback(
                            f"🔍 Checking websites for Google Ads / FB Pixel..."
                        )
                    leads = await _check_ads_for_leads(
                        leads, progress_callback, cancel_event
                    )

                all_leads.extend(leads)

            except Exception as e:
                logger.exception(f"Error scraping sub-district '{sub_location}'")
                if progress_callback:
                    progress_callback(f"❌ Error on '{sub_location}': {e}")
            finally:
                await context.close()

            # Human-like delay between sub-districts
            await human_delay(3, 7)

    finally:
        await close_browser(p, browser)

    # 5. Find social media links for all collected leads
    if all_leads:
        if progress_callback:
            progress_callback(
                f"🔍 Finding social media links for {len(all_leads)} leads..."
            )
        all_leads = await _find_social_for_leads(
            all_leads, progress_callback, cancel_event
        )

    # 6. Clean & export results
    if all_leads:
        if progress_callback:
            progress_callback(f"🧼 Cleaning {len(all_leads)} leads...")

        # --- Data Cleaning Pipeline ---
        cleaned = clean_leads(all_leads)
        total_before = len(all_leads)
        total_after = len(cleaned)
        removed = total_before - total_after
        if removed > 0:
            if progress_callback:
                progress_callback(
                    f"🧹 Removed {removed} duplicate / low-value lead(s). "
                    f"{total_after} unique lead(s) remaining."
                )

        if progress_callback:
            progress_callback(f"💾 Saving {len(cleaned)} cleaned leads...")

        # Save to CSV
        await _save_to_csv(cleaned)

        # Generate watermarked PDF
        await _generate_pdf_report(cleaned)

        # Export formatted Excel (.xlsx)
        try:
            xlsx_path = export_to_xlsx(cleaned)
            if progress_callback:
                progress_callback(f"📊 Excel spreadsheet: {xlsx_path}")
        except Exception as e:
            logger.warning(f"XLSX export skipped: {e}")
            if progress_callback:
                progress_callback(f"⚠️ XLSX export skipped: {e}")

        # Save to database
        try:
            init_db()
            save_leads(cleaned)
            if progress_callback:
                progress_callback("🗄️ Database updated.")
        except Exception as e:
            logger.warning(f"Database save skipped: {e}")
            if progress_callback:
                progress_callback(f"⚠️ Database save skipped: {e}")

        if progress_callback:
            progress_callback(
                f"✅ All data saved for keyword='{keyword}', location='{location}'"
            )
    else:
        if progress_callback:
            progress_callback("⚠️ No leads found to save.")

    return all_leads


async def _check_ads_for_leads(
    leads: list[dict],
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[dict]:
    """Iterate over leads and check their websites for ads."""
    for i, lead in enumerate(leads):
        if cancel_event and cancel_event.is_set():
            break

        if lead.get("website"):
            if progress_callback:
                progress_callback(
                    f"🔎 Checking ads ({i + 1}/{len(leads)}): {lead.get('name', 'Unknown')}"
                )
            try:
                ads_result = await check_website_for_ads(lead["website"])
                lead["has_google_ads"] = ads_result.get("has_google_ads", False)
                lead["has_facebook_pixel"] = ads_result.get("has_facebook_pixel", False)
            except Exception as e:
                logger.debug(f"Ads check failed for {lead['website']}: {e}")
                lead["has_google_ads"] = False
                lead["has_facebook_pixel"] = False
        else:
            lead["has_google_ads"] = False
            lead["has_facebook_pixel"] = False

    return leads


async def _find_social_for_leads(
    leads: list[dict],
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[threading.Event] = None,
) -> list[dict]:
    """
    Iterate over leads and find social media links + email from their websites.
    Uses enrich_website_data which makes ONE HTTP request per lead.
    """
    for i, lead in enumerate(leads):
        if cancel_event and cancel_event.is_set():
            break

        if lead.get("website"):
            if progress_callback:
                progress_callback(
                    f"📱 Enriching ({i + 1}/{len(leads)}): {lead.get('name', 'Unknown')}"
                )
            try:
                enriched = await asyncio.to_thread(
                    enrich_website_data, lead["website"]
                )
                lead["instagram"] = enriched.get("instagram")
                lead["facebook"] = enriched.get("facebook")
                lead["tiktok"] = enriched.get("tiktok")
                lead["email"] = enriched.get("email")
            except Exception as e:
                logger.debug(f"Enricher failed for {lead['website']}: {e}")
                lead["instagram"] = None
                lead["facebook"] = None
                lead["tiktok"] = None
                lead["email"] = None
        else:
            lead["instagram"] = None
            lead["facebook"] = None
            lead["tiktok"] = None
            lead["email"] = None

    return leads


async def _save_to_csv(leads: list[dict]) -> str:
    """Save leads to a CSV file in the output directory."""
    filepath = os.path.join(OUTPUT_DIR, DEFAULT_CSV_NAME)

    if not leads:
        return filepath

    # 12-column premium schema — reordered
    fieldnames = [
        "no",
        "name",
        "address",
        "phone",
        "email",
        "instagram",
        "tiktok",
        "facebook",
        "website",
        "punya_ads",
        "rating",
        "reviews_count",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, lead in enumerate(leads, start=1):
            row = {
                "no": idx,
                "name": lead.get("name", ""),
                "address": lead.get("address", ""),
                "phone": lead.get("phone", ""),
                "email": lead.get("email", ""),
                "instagram": lead.get("instagram", ""),
                "tiktok": lead.get("tiktok", ""),
                "facebook": lead.get("facebook", ""),
                "website": lead.get("website", ""),
                "punya_ads": "✅ Yes" if lead.get("has_google_ads") or lead.get("has_facebook_pixel") else "❌ No",
                "rating": lead.get("rating", ""),
                "reviews_count": lead.get("reviews_count", ""),
            }
            writer.writerow(row)

    logger.info(f"CSV saved: {filepath}")
    return filepath


async def _generate_pdf_report(leads: list[dict]) -> str:
    """Generate a watermarked PDF report."""
    filepath = generate_pdf(
        leads=leads,
        filename=DEFAULT_PDF_NAME,
        title=f"Google Maps Leads – {leads[0].get('keyword', 'N/A')} in {leads[0].get('location', 'N/A')}",
    )
    return filepath


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main_cli():
    """Direct CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Google Maps Leads Scraper – CLI mode"
    )
    parser.add_argument("--keyword", "-k", required=True, help="Search keyword (e.g. Plumber)")
    parser.add_argument("--location", "-l", required=True, help="Location (e.g. Austin, Texas)")
    parser.add_argument(
        "--no-ads-check", action="store_true", help="Skip Google Ads / FB Pixel check"
    )
    args = parser.parse_args()

    async def _run():
        await run_scraper(
            keyword=args.keyword,
            location=args.location,
            enable_ads_check=not args.no_ads_check,
            progress_callback=lambda msg: print(msg),
        )

    asyncio.run(_run())


if __name__ == "__main__":
    main_cli()