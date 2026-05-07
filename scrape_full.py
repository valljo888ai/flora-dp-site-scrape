"""
scrape_full.py — Designer Plants — Multi-Catalog Full Deterministic Scraper
============================================================================
Phases (per catalog):
  1. Load More crawl  →  click button.load-more-button-new until gone, collect product URLs
  2. Product scrape   →  Playwright, async, extract all 26 fields per product page
  3. CSV assembly     →  one CSV per catalog + validation

Pre-requisite (one time only):
  python login.py      →  saves auth.json next to this file

Usage:
  python scrape_full.py                             # all catalogs
  python scrape_full.py --catalog outdoor           # one catalog only
  python scrape_full.py --test                      # first load only per catalog (faster)
  python scrape_full.py --no-headless               # show browser window
  python scrape_full.py --concurrency 5             # Playwright pages in parallel (default 3)

Available --catalog values:
  outdoor | verticalgardens
"""

import argparse
import asyncio
import csv
import pathlib
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = pathlib.Path(__file__).parent
AUTH_FILE = HERE / "auth.json"

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL   = "https://designerplants.com.au"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Catalog definitions ────────────────────────────────────────────────────────
CATALOGS = {
    "outdoor":        {"label": "Outdoor Plants",   "category_url": "/product-category/artificial-outdoor-plants/",  "output": HERE / "dp_outdoor_full.csv"},
    "verticalgardens": {"label": "Vertical Gardens", "category_url": "/product-category/vertical-garden-green-walls/", "output": HERE / "dp_verticalgardens_full.csv"},
}

FIELDNAMES = [
    "category", "product_url", "product_id", "sku", "name",
    "in_stock",
    "breadcrumb", "short_description", "description",
    "sale_price", "regular_price", "retail_price", "wholesale_price",
    "save_amount", "variable_price_range",
    "rating", "review_count",
    "seo_title", "meta_description",
    "image_1", "image_2", "image_3", "image_4", "image_5",
    "scraped_at",
    "scrape_status",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

class SessionExpiredError(Exception):
    pass


def canonical_url(href: str) -> str:
    """Strip query params and trailing slash from product URL."""
    return href.split("?")[0].rstrip("/")


def parse_product_id(url: str) -> str:
    """
    Extract product identifier from WooCommerce URL.
    /product/slug-name/ → 'slug-name'
    Falls back to full URL path if pattern doesn't match.
    """
    m = re.search(r"/product/([^/]+)/?$", url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]
