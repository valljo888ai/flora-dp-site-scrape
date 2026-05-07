# FLORA DP Site Scrape Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Playwright scraper for designerplants.com.au that exports all products from 2 WooCommerce categories to CSV files, structured identically to the FLORA FI Site Scrape project.

**Architecture:** 3-phase pipeline per catalog — (1) Load More crawl collects all product URLs, (2) async Playwright scrapes each product page in parallel, (3) CSV assembly + per-catalog coverage validation. A `verify.py` script re-crawls both categories post-run and checks coverage, critical fields, and data integrity.

**Tech Stack:** Python 3.10+, Playwright (async), csv (stdlib), asyncio (stdlib)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `scrape_full.py` | Create | Pipeline engine — all scraping logic |
| `verify.py` | Create | Post-scrape data verification |
| `save_session.py` | Create | Headless auto-login, writes `auth.json` |
| `login.py` | Create | Manual browser login, writes `auth.json` |
| `run.bat` | Create | Windows launcher — loops catalogs + verify |
| `login.bat` | Create | Windows wrapper for `login.py` |
| `setup.bat` | Create | One-time dependency installer |

No test files — this project has no unit-testable logic separate from live network calls. Correctness is verified by `--test` mode (scrapes first load of each catalog) and `verify.py` (post-run data check).

---

## Task 1: Project scaffold + setup.bat + login.bat

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\setup.bat`
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\login.bat`

- [ ] **Step 1: Create setup.bat**

```bat
@echo off
cd /d "%~dp0"
echo ============================================================
echo  Designer Plants Scraper — Dependency Setup
echo ============================================================
echo.

echo [1/2] Installing Python packages...
pip install playwright
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Make sure Python is installed and on PATH.
    pause
    exit /b 1
)

echo.
echo [2/2] Downloading Chromium browser (~300MB, may take a few minutes)...
python -m playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo ERROR: Chromium install failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Setup complete!
echo  Next step: run login.bat to save your Designer Plants session,
echo  then use run.bat to scrape any time.
echo ============================================================
pause
```

Save to `setup.bat`.

- [ ] **Step 2: Create login.bat**

```bat
@echo off
cd /d "%~dp0"
echo ============================================================
echo  Designer Plants Scraper — Save Login Session
echo ============================================================
echo.
echo A browser window will open. Log in to your Designer Plants account,
echo then return here and press Enter to save the session.
echo.
python login.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Login failed. See message above.
    pause
    exit /b 1
)
echo.
echo Session saved. You can now run run.bat to scrape anytime.
pause
```

Save to `login.bat`.

- [ ] **Step 3: Commit**

```bash
git add setup.bat login.bat
git commit -m "feat: add setup.bat and login.bat launchers"
```

---

## Task 2: login.py — Manual browser login

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\login.py`

- [ ] **Step 1: Create login.py**

```python
"""
login.py — One-time Designer Plants auth session saver
Run this once to log in and save your session. After that, scrape_full.py
uses the saved session automatically — no further logins needed.

Usage:
    python login.py
"""

import pathlib
import sys
from playwright.sync_api import sync_playwright

HERE      = pathlib.Path(__file__).parent
AUTH_FILE = HERE / "auth.json"
LOGIN_URL = "https://designerplants.com.au/my-account/"
CHECK_URL = "https://designerplants.com.au/product-category/artificial-outdoor-plants/"


def main():
    print("=" * 60)
    print("  Designer Plants — One-time login")
    print("=" * 60)

    if AUTH_FILE.exists():
        overwrite = input(
            f"\nauth.json already exists ({AUTH_FILE}).\n"
            "Overwrite with a new session? [y/N] "
        ).strip().lower()
        if overwrite != "y":
            print("Aborted — existing auth.json kept.")
            sys.exit(0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = context.new_page()

        print(f"\nOpening browser → {LOGIN_URL}")
        page.goto(LOGIN_URL)

        print("\nPlease log in to your Designer Plants account in the browser window.")
        print("When you are fully logged in and can browse products,")
        print("press Enter here to save the session ...")
        input()

        # Verify we are actually logged in
        page.goto(CHECK_URL)
        page.wait_for_load_state("domcontentloaded")
        if "my-account" in page.url or "login" in page.url:
            print("\nWarning: looks like you may not be logged in yet.")
            print("Please try again and make sure you can see products.")
            browser.close()
            sys.exit(1)

        context.storage_state(path=str(AUTH_FILE))
        browser.close()

    print(f"\nSession saved to {AUTH_FILE}")
    print("  You can now run: python scrape_full.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add login.py
git commit -m "feat: add login.py manual session saver"
```

---

## Task 3: save_session.py — Headless auto-login

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\save_session.py`

This is used by `run.bat` before each catalog to silently refresh the session without a visible browser window.

- [ ] **Step 1: Inspect live login page to confirm field names**

Before writing, open the DP login page in a browser and check the username field name attribute. WooCommerce typically uses `input[name="username"]`. If the site uses `input[name="email"]` instead, update the selector in the script below accordingly.

URL to check: `https://designerplants.com.au/my-account/`

- [ ] **Step 2: Create save_session.py**

```python
"""
One-shot script: log in headlessly and save storage_state to auth.json.
Used by run.bat to refresh the session before each catalog without
popping up a visible browser window.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL   = "https://designerplants.com.au"
AUTH_FILE  = Path(__file__).parent / "auth.json"
USERNAME   = "floradesigns.com.au"
PASSWORD   = "rfvEhnn9kc#O"
LOGIN_URL  = f"{BASE_URL}/my-account/"
CHECK_URL  = f"{BASE_URL}/product-category/artificial-outdoor-plants/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page    = await context.new_page()

        print("Navigating to login page...")
        await page.goto(LOGIN_URL, wait_until="networkidle")

        print("Filling credentials...")
        # WooCommerce typically uses input[name="username"] — verify on live site
        await page.fill('input[name="username"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)

        print("Submitting login form...")
        await page.click('button[name="login"]')

        # Wait for redirect away from /my-account/ login state
        try:
            await page.wait_for_url(
                lambda url: "my-account" not in url or "orders" in url or "dashboard" in url,
                timeout=15000
            )
            print(f"Logged in — current URL: {page.url}")
        except Exception:
            print(f"WARNING: still on {page.url} after 15s — may not be logged in")

        # Verify access to a category page
        print("Verifying session...")
        await page.goto(CHECK_URL, wait_until="networkidle")
        if "my-account" in page.url or "login" in page.url:
            print("ERROR: Redirected to login — session not valid. Check credentials.")
            await browser.close()
            return

        print(f"Session valid — on: {page.url}")

        storage = await context.storage_state()
        AUTH_FILE.write_text(json.dumps(storage, indent=2))
        print(f"auth.json saved to: {AUTH_FILE}")

        await browser.close()


asyncio.run(main())
```

- [ ] **Step 3: Test save_session.py manually**

```
python save_session.py
```

Expected output ending with: `auth.json saved to: ...\auth.json`

If it prints `ERROR: Redirected to login`, check whether the login field is `username` or `email` and update the `page.fill` selector accordingly. Also confirm the submit button selector — WooCommerce may use `button[name="login"]` or `input[type="submit"]`.

- [ ] **Step 4: Commit**

```bash
git add save_session.py auth.json
git commit -m "feat: add save_session.py headless auto-login"
```

---

## Task 4: scrape_full.py — Constants, catalog config, FIELDNAMES

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\scrape_full.py`

Build the file incrementally across Tasks 4–7. This task creates the skeleton — constants, catalog config, field list, helpers, and the SessionExpiredError class.

- [ ] **Step 1: Create scrape_full.py with constants and FIELDNAMES**

```python
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
```

- [ ] **Step 2: Commit skeleton**

```bash
git add scrape_full.py
git commit -m "feat: scrape_full.py skeleton — constants, catalogs, FIELDNAMES"
```

---

## Task 5: scrape_full.py — Phase 1 (Load More crawl)

**Files:**
- Modify: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\scrape_full.py`

Append Phase 1 to the file created in Task 4.

- [ ] **Step 1: Append phase1_crawl to scrape_full.py**

Add this block after the helpers section:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — Load More crawl
# ═══════════════════════════════════════════════════════════════════════════════

async def phase1_crawl(page, category_url: str, test_mode: bool = False) -> list[str]:
    """
    Navigate to category, click 'Load More' until exhausted, return
    deduplicated canonical product URLs.

    Raises SessionExpiredError if the page redirects to login.
    """
    full_url = BASE_URL + category_url
    await page.goto(full_url, wait_until="domcontentloaded", timeout=30_000)

    if "my-account" in page.url or "login" in page.url:
        raise SessionExpiredError(
            "Session expired — re-run login.bat to refresh your auth.json"
        )

    urls: set[str] = set()

    async def collect_current() -> int:
        """Collect all product links currently visible; return count of new ones added."""
        links = await page.eval_on_selector_all(
            "a.woocommerce-LoopProduct-link",
            "els => els.map(el => el.href)"
        )
        before = len(urls)
        for href in links:
            urls.add(canonical_url(href))
        return len(urls) - before

    # Initial collection
    added = await collect_current()
    print(f"  Initial load: {len(urls)} products")

    if test_mode:
        return list(urls)

    # Click Load More until it disappears or adds nothing new
    rounds = 0
    while True:
        btn = await page.query_selector("button.load-more-button-new")
        if btn is None:
            break
        is_visible = await btn.is_visible()
        if not is_visible:
            break

        await btn.click()
        # Wait for new products to render
        await page.wait_for_load_state("networkidle", timeout=15_000)

        added = await collect_current()
        rounds += 1
        print(f"  Load More #{rounds}: +{added} new  ({len(urls)} total)")

        if added == 0:
            # Button still present but nothing new — stop to avoid infinite loop
            print("  No new products after click — stopping pagination.")
            break

    return list(urls)
```

- [ ] **Step 2: Commit**

```bash
git add scrape_full.py
git commit -m "feat: phase1_crawl — Load More pagination"
```

---

## Task 6: scrape_full.py — Phase 2 (product scrape) + Phase 3 (CSV)

**Files:**
- Modify: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\scrape_full.py`

Append Phase 2 and Phase 3 functions.

- [ ] **Step 1: Append scrape_product, phase2_scrape, phase3 helpers**

Add after the Phase 1 block:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Product scrape
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape_product(context, url: str, category_label: str, scraped_at: str) -> dict:
    """
    Visit a single product page and extract all 26 fields.
    Returns a dict keyed by FIELDNAMES.
    On any error, returns a partial row with scrape_status='failed'.
    """
    row = {f: "" for f in FIELDNAMES}
    row["product_url"]   = url
    row["category"]      = category_label
    row["scraped_at"]    = scraped_at
    row["product_id"]    = parse_product_id(url)
    row["scrape_status"] = "ok"

    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        if "my-account" in page.url or "login" in page.url:
            raise SessionExpiredError("Session expired mid-scrape")

        # Render gate — wait for product title to confirm full page load
        await page.wait_for_selector("h1", timeout=30_000)

        async def text(sel: str) -> str:
            try:
                return (await page.eval_on_selector(sel, "el => el.textContent.trim()")) or ""
            except Exception:
                return ""

        async def attr(sel: str, attribute: str) -> str:
            try:
                return (await page.eval_on_selector(sel, f"el => el.getAttribute('{attribute}')")) or ""
            except Exception:
                return ""

        # Canonical URL
        row["product_url"] = await attr("link[rel='canonical']", "href") or url

        # Identity
        row["sku"]  = await text("p.product-sku")
        # Strip non-digit chars to match webscraper.io regex [0-9]+
        sku_digits = re.sub(r"\D", "", row["sku"])
        if sku_digits:
            row["sku"] = sku_digits
        row["name"] = await text("h1")

        # Stock
        row["in_stock"] = await text("p.stock-status")

        # Content
        row["breadcrumb"]         = await text(".woocommerce-breadcrumb")
        row["short_description"]  = await text(".woocommerce-product-details__short-description")
        row["description"]        = await text(".single_description_acc div.open")

        # Pricing
        row["sale_price"]           = await text(".mainsale-price .sale-price .woocommerce-Price-amount bdi")
        row["regular_price"]        = await text(".mainsale-price .regular-price .woocommerce-Price-amount bdi")
        row["retail_price"]         = await text("p.price.no-sale .woocommerce-Price-amount bdi")
        row["wholesale_price"]      = await text(".price_custom .woocommerce-Price-amount bdi")
        row["save_amount"]          = await text(".saveprice .woocommerce-Price-amount bdi")
        row["variable_price_range"] = await text(".variations_form ~ * .price, .single_variation_wrap .price")

        # Ratings
        rating_raw = await text(".star-rating")
        rating_m   = re.search(r"[0-9]+\.[0-9]+", rating_raw)
        row["rating"] = rating_m.group(0) if rating_m else ""

        review_raw = await text(".woocommerce-review-link")
        review_m   = re.search(r"[0-9]+", review_raw)
        row["review_count"] = review_m.group(0) if review_m else ""

        # SEO
        row["seo_title"]       = await text("title")
        row["meta_description"] = await page.get_attribute('meta[property="og:description"]', "content") or ""

        # Images — collect up to 5 data-large_image attributes
        image_els = await page.query_selector_all(".wpgs-for img[data-large_image]")
        for i, img_el in enumerate(image_els[:5], start=1):
            val = await img_el.get_attribute("data-large_image") or ""
            row[f"image_{i}"] = val

    except SessionExpiredError:
        await page.close()
        raise
    except PlaywrightTimeoutError:
        print(f"  WARN timeout: {url}")
        row["scrape_status"] = "failed"
    except Exception as exc:
        print(f"  WARN {url}: {exc}")
        row["scrape_status"] = "failed"
    finally:
        try:
            await page.close()
        except Exception:
            pass

    return row


async def phase2_scrape(
    context,
    urls: list[str],
    category_label: str,
    concurrency: int = 3,
) -> list[dict]:
    """
    Scrape all product URLs concurrently using a semaphore.
    Returns list of row dicts in completion order.
    Auto-retries any failed rows once.
    """
    scraped_at = datetime.now(timezone.utc).isoformat()
    semaphore  = asyncio.Semaphore(concurrency)
    total      = len(urls)
    completed  = 0

    async def fetch_one(url: str) -> dict:
        nonlocal completed
        async with semaphore:
            row = await scrape_product(context, url, category_label, scraped_at)
        completed += 1
        if completed % 25 == 0 or completed == total:
            print(f"  [{completed}/{total}] products scraped")
        return row

    rows = list(await asyncio.gather(*[fetch_one(u) for u in urls]))

    # Retry failed rows once
    failed_urls = [r["product_url"] for r in rows if r["scrape_status"] == "failed"]
    if failed_urls:
        print(f"  Retrying {len(failed_urls)} failed products...")
        retry_rows = list(await asyncio.gather(*[fetch_one(u) for u in failed_urls]))
        retry_map  = {r["product_url"]: r for r in retry_rows}
        rows = [retry_map.get(r["product_url"], r) if r["scrape_status"] == "failed" else r for r in rows]

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — CSV assembly, validation, summary
# ═══════════════════════════════════════════════════════════════════════════════

def phase3_write_csv(rows: list[dict], output_path: pathlib.Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


async def validate(page, category_url: str, scraped_urls: list[str]) -> bool:
    """
    Re-crawl the category and assert every URL found appears in scraped_urls.
    """
    print("\n-- Validation --")
    expected = await phase1_crawl(page, category_url, test_mode=False)
    scraped  = set(scraped_urls)
    missing  = [u for u in expected if u not in scraped]

    print(f"  Expected: {len(expected)}  Scraped: {len(scraped)}  Missing: {len(missing)}")
    if missing:
        print("  Missing URLs:")
        for u in sorted(missing):
            print(f"    {u}")

    if len(expected) == 0 and len(scraped) > 0:
        print("  WARNING: re-crawl returned 0 URLs — possible block during validation")
        return False

    ok = len(missing) == 0
    print(f"  Coverage OK: {ok}")
    return ok


def print_summary(rows: list[dict], output_path: pathlib.Path, elapsed: float) -> None:
    stock_counter = Counter()
    for row in rows:
        status = row.get("in_stock", "") or "Unknown"
        stock_counter[status] += 1

    print(f"\n{'='*55}")
    print(f"  {len(rows)} products written to {output_path.name}")
    print(f"  Total time: {elapsed:.1f}s")
    print(f"\n  Stock breakdown:")
    for status, n in sorted(stock_counter.items()):
        print(f"    {status}: {n}")
    print(f"{'='*55}")
```

- [ ] **Step 2: Commit**

```bash
git add scrape_full.py
git commit -m "feat: phase2 product scraper + phase3 CSV writer"
```

---

## Task 7: scrape_full.py — Per-catalog runner + main()

**Files:**
- Modify: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\scrape_full.py`

Append the catalog runner and CLI entry point.

- [ ] **Step 1: Append run_catalog_async and main()**

Add after the Phase 3 block:

```python
# ═══════════════════════════════════════════════════════════════════════════════
# Per-catalog runner
# ═══════════════════════════════════════════════════════════════════════════════

async def run_catalog_async(catalog_key: str, catalog_config: dict, args) -> None:
    label        = catalog_config["label"]
    category_url = catalog_config["category_url"]
    output_csv   = catalog_config["output"]

    print(f"\n{'#'*60}")
    print(f"# CATALOG : {label}")
    print(f"# Output  : {output_csv.name}")
    print(f"{'#'*60}")

    t_start = time.time()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            storage_state=str(AUTH_FILE),
            viewport={"width": 1280, "height": 800},
            user_agent=USER_AGENT,
        )
        nav_page = await context.new_page()

        # ── Phase 1 ───────────────────────────────────────────────────────────
        print(f"\n=== Phase 1: Category crawl (Load More) ===")
        t1 = time.time()
        try:
            urls = await phase1_crawl(nav_page, category_url, test_mode=args.test)
        except SessionExpiredError as e:
            print(f"\nERROR: {e}")
            await browser.close()
            sys.exit(1)
        print(f"Phase 1 done in {time.time()-t1:.1f}s  —  {len(urls)} products")

        # ── Phase 2 ───────────────────────────────────────────────────────────
        print(f"\n=== Phase 2: Product scrape ({args.concurrency} concurrent pages) ===")
        t2 = time.time()
        try:
            rows = await phase2_scrape(context, urls, label, concurrency=args.concurrency)
        except SessionExpiredError as e:
            print(f"\nERROR: {e}")
            print("Session expired mid-scrape — re-run login.bat then re-run this catalog.")
            await browser.close()
            sys.exit(1)
        print(f"Phase 2 done in {time.time()-t2:.1f}s")

        # ── Phase 3 ───────────────────────────────────────────────────────────
        print(f"\n=== Phase 3: Assembling CSV ===")
        phase3_write_csv(rows, output_csv)

        # ── Validation ────────────────────────────────────────────────────────
        scraped_urls = [r["product_url"] for r in rows if r["product_url"]]
        await validate(nav_page, category_url, scraped_urls)

        await browser.close()

    print_summary(rows, output_csv, time.time() - t_start)


def run_catalog(catalog_key: str, catalog_config: dict, args) -> None:
    asyncio.run(run_catalog_async(catalog_key, catalog_config, args))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Designer Plants multi-catalog scraper")
    parser.add_argument(
        "--catalog", default="all",
        choices=["all"] + list(CATALOGS.keys()),
        help="Which catalog to scrape (default: all). Ignored if --catalogs is set.",
    )
    parser.add_argument(
        "--catalogs", default=None,
        help="Comma-separated list of catalogs, e.g. --catalogs outdoor,verticalgardens",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Scrape first load of each catalog only (quick validation run)",
    )
    parser.add_argument(
        "--no-headless", dest="headless", action="store_false", default=True,
        help="Show the browser window during scraping",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="Playwright pages open in parallel during Phase 2 (default: 3).",
    )
    args = parser.parse_args()

    if not AUTH_FILE.exists():
        print(f"ERROR: {AUTH_FILE} not found.")
        print("Run  python login.py  first to save your session.")
        sys.exit(1)

    if args.catalogs:
        to_run = [k.strip() for k in args.catalogs.split(",") if k.strip()]
        unknown = [k for k in to_run if k not in CATALOGS]
        if unknown:
            print(f"ERROR: unknown catalog key(s): {', '.join(unknown)}")
            print(f"Valid keys: {', '.join(CATALOGS.keys())}")
            sys.exit(1)
    else:
        to_run = list(CATALOGS.keys()) if args.catalog == "all" else [args.catalog]

    session_start = time.time()
    for key in to_run:
        run_catalog(key, CATALOGS[key], args)

    if len(to_run) > 1:
        print(f"\nAll {len(to_run)} catalogs complete in {time.time()-session_start:.1f}s")
        print("Output files:")
        for key in to_run:
            print(f"  {CATALOGS[key]['output'].name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test scrape_full.py in --test mode**

First confirm `auth.json` exists (run `python save_session.py` if not). Then:

```
python scrape_full.py --test --catalog outdoor --no-headless
```

Expected: Phase 1 prints product count from first load, Phase 2 scrapes those products, Phase 3 writes `dp_outdoor_full.csv`, validation prints "Coverage OK: True" (or close — test mode only scrapes first load so some miss is expected). No Python exceptions.

- [ ] **Step 3: Commit**

```bash
git add scrape_full.py
git commit -m "feat: run_catalog runner + main CLI entry point"
```

---

## Task 8: verify.py — Post-scrape data verification

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\verify.py`

- [ ] **Step 1: Create verify.py**

```python
"""
verify.py — Post-scrape data verification.

Runs three checks against dp_outdoor_full.csv and dp_verticalgardens_full.csv:

  1. Coverage:        re-crawl every category (Load More) and confirm all
                      currently-listed product URLs are present in the CSVs.
  2. Critical fields: every row has product_url, sku, name, wholesale_price,
                      in_stock, image_1 populated.
  3. Integrity:       no duplicate product_url values; in_stock values from
                      known set; image_1 starts with 'http'.

Exits 0 on PASS, 1 on FAIL. Extras (CSV rows not on site) reported as INFO.

Usage:
  python verify.py

Requires auth.json to exist (run save_session.py or login.bat first).
"""
import asyncio
import csv
import pathlib
import sys
from collections import Counter
from playwright.async_api import async_playwright

HERE      = pathlib.Path(__file__).parent
AUTH_FILE = HERE / "auth.json"
BASE_URL  = "https://designerplants.com.au"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

CATALOGS = {
    "outdoor":         "/product-category/artificial-outdoor-plants/",
    "verticalgardens": "/product-category/vertical-garden-green-walls/",
}

CRITICAL_FIELDS = [
    "product_url", "sku", "name", "wholesale_price", "in_stock", "image_1",
]

KNOWN_STOCK_STATUSES = {"In stock", "Out of stock", "On backorder", ""}


def canonical(href: str) -> str:
    return href.split("?")[0].rstrip("/")


async def crawl_category(page, cat_url: str) -> set[str]:
    """Re-crawl a category using Load More until exhausted. Returns set of canonical URLs."""
    full_url = BASE_URL + cat_url
    await page.goto(full_url, wait_until="domcontentloaded", timeout=30_000)
    if "my-account" in page.url or "login" in page.url:
        raise RuntimeError("Session expired during verification — re-run save_session.py")

    urls: set[str] = set()

    async def collect():
        links = await page.eval_on_selector_all(
            "a.woocommerce-LoopProduct-link",
            "els => els.map(el => el.href)"
        )
        for href in links:
            urls.add(canonical(href))

    await collect()

    while True:
        btn = await page.query_selector("button.load-more-button-new")
        if btn is None or not await btn.is_visible():
            break
        before = len(urls)
        await btn.click()
        await page.wait_for_load_state("networkidle", timeout=15_000)
        await collect()
        if len(urls) == before:
            break

    return urls


def load_csv(catalog_key: str) -> list[dict] | None:
    path = HERE / f"dp_{catalog_key}_full.csv"
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_critical_fields(all_rows: list[dict]) -> list[str]:
    issues = []
    for fld in CRITICAL_FIELDS:
        empties = [r for r in all_rows if not r.get(fld, "").strip()]
        if empties:
            issues.append(f"{len(empties)} row(s) missing critical field '{fld}'")
            for r in empties[:3]:
                issues.append(f"    e.g. {r.get('_catalog', '?')}: {r.get('product_url', '?')}")
    return issues


def check_integrity(all_rows: list[dict]) -> list[str]:
    issues = []

    url_counts = Counter(r["product_url"] for r in all_rows)
    dups = [u for u, n in url_counts.items() if n > 1]
    if dups:
        issues.append(f"{len(dups)} duplicate product_url(s) across CSVs")

    bad_status = [r for r in all_rows if r.get("in_stock", "") not in KNOWN_STOCK_STATUSES]
    if bad_status:
        issues.append(f"{len(bad_status)} row(s) with unexpected in_stock value")
        for r in bad_status[:3]:
            issues.append(f"    e.g. {r.get('_catalog', '?')}: in_stock={r['in_stock']!r}")

    bad_images = [r for r in all_rows if r.get("image_1", "") and not r["image_1"].startswith("http")]
    if bad_images:
        issues.append(f"{len(bad_images)} row(s) with malformed image_1 URL")

    return issues


async def main() -> int:
    print("=" * 60)
    print("  Designer Plants — Data Verification")
    print("=" * 60)

    if not AUTH_FILE.exists():
        print(f"ERROR: {AUTH_FILE} not found — run save_session.py or login.bat first.")
        return 1

    # Load CSVs
    csv_data = {}
    missing_csvs = []
    for key in CATALOGS:
        rows = load_csv(key)
        if rows is None:
            missing_csvs.append(key)
        else:
            for r in rows:
                r["_catalog"] = key
            csv_data[key] = rows

    if missing_csvs:
        print(f"FAIL: missing CSV files for: {', '.join(missing_csvs)}")
        return 1

    all_rows = [r for rows in csv_data.values() for r in rows]
    total = len(all_rows)
    print(f"\nLoaded {total} rows across {len(CATALOGS)} CSVs.")

    # Coverage check
    print("\n[1/3] Coverage check — re-crawling categories ...")
    print(f"      {'Catalog':18} {'Site':>6} {'CSV':>6} {'Match':>7} {'Missing':>9} {'Extra':>6}")
    print("      " + "-" * 53)

    coverage_failures = []
    coverage_extras   = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            storage_state=str(AUTH_FILE), user_agent=USER_AGENT,
        )
        page = await context.new_page()
        try:
            for key, cat_url in CATALOGS.items():
                site_urls = await crawl_category(page, cat_url)
                csv_urls  = {r["product_url"] for r in csv_data[key]}
                missing   = site_urls - csv_urls
                extra     = csv_urls - site_urls
                match_str = "OK" if not missing else "FAIL"
                print(f"      {key:18} {len(site_urls):>6} {len(csv_urls):>6} {match_str:>7} {len(missing):>9} {len(extra):>6}")
                if missing:
                    coverage_failures.append((key, missing))
                if extra:
                    coverage_extras.append((key, extra))
        finally:
            await browser.close()

    # Critical fields
    print("\n[2/3] Critical fields check ...")
    field_issues = check_critical_fields(all_rows)
    if field_issues:
        for msg in field_issues:
            print(f"      {msg}")
    else:
        print(f"      OK — all {total} rows have all {len(CRITICAL_FIELDS)} critical fields populated.")

    # Integrity
    print("\n[3/3] Integrity checks ...")
    integrity_issues = check_integrity(all_rows)
    if integrity_issues:
        for msg in integrity_issues:
            print(f"      {msg}")
    else:
        print("      OK — no duplicates, stock values and image URLs clean.")

    # Stock breakdown
    status_counts = Counter(r.get("in_stock", "") for r in all_rows)
    print(f"\nStock breakdown across all {total} products:")
    for status, n in status_counts.most_common():
        label = status if status else "(empty)"
        print(f"  {label}: {n}")

    if coverage_extras:
        total_extras = sum(len(e) for _, e in coverage_extras)
        print(f"\nINFO: {total_extras} CSV row(s) describe products no longer listed in their category")
        print("      (de-listed between scrape and verification — not a failure)")
        for cat, extras in coverage_extras:
            for u in sorted(extras)[:3]:
                print(f"        {cat}: {u}")
            if len(extras) > 3:
                print(f"        ... and {len(extras) - 3} more in {cat}")

    # Verdict
    print("\n" + "=" * 60)
    failed = bool(coverage_failures or field_issues or integrity_issues)
    if failed:
        print("  VERIFICATION FAILED — see issues above")
        if coverage_failures:
            print(f"  Missing products by catalog:")
            for cat, missing in coverage_failures:
                print(f"    {cat}: {len(missing)} missing — re-run: run.bat --catalog {cat}")
        print("=" * 60)
        return 1
    print("  VERIFICATION PASSED — all checks green")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Commit**

```bash
git add verify.py
git commit -m "feat: add verify.py post-scrape data verification"
```

---

## Task 9: run.bat — Full run launcher

**Files:**
- Create: `C:\Users\admin\Desktop\Claude\Development\FLORA DP Site Scrape\run.bat`

- [ ] **Step 1: Create run.bat**

```bat
@echo off
cd /d "%~dp0"
echo ============================================================
echo  Designer Plants Scraper — Full Run
echo ============================================================
echo.

:: If args were passed, treat as single-catalog or option passthrough
if not "%~1"=="" goto single_catalog

:: No args — run all 2 catalogs with a session refresh before each
echo Running all catalogs with session refresh between each.
echo.

for %%C in (outdoor verticalgardens) do (
    echo ------------------------------------------------------------
    echo  Refreshing session before catalog: %%C
    echo ------------------------------------------------------------
    python save_session.py
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Session refresh failed for catalog %%C. See output above.
        pause
        exit /b 1
    )
    echo.
    echo Running catalog: %%C
    python scrape_full.py --catalog %%C --concurrency 3
    if %ERRORLEVEL% neq 0 (
        echo ERROR: Scraper exited with an error on catalog %%C. See output above.
        pause
        exit /b 1
    )
    echo.
)

:: All catalogs scraped — run data verification
echo ------------------------------------------------------------
echo  Refreshing session before verification
echo ------------------------------------------------------------
python save_session.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Session refresh failed before verification.
    pause
    exit /b 1
)
echo.
python verify.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ============================================================
    echo  Scrape completed but verification reported issues above.
    echo  Check the FAIL details and re-run any affected catalog.
    echo ============================================================
    pause
    exit /b 1
)

goto done

:single_catalog
:: Single catalog or --test etc. — refresh session once then run
echo Refreshing session...
python save_session.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Session refresh failed. See output above.
    pause
    exit /b 1
)
echo.
python scrape_full.py %*
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Scraper exited with an error. See output above.
    pause
    exit /b 1
)

:done
echo.
echo ============================================================
echo  Done! CSV files are ready and verified.
echo ============================================================
pause
```

- [ ] **Step 2: Commit**

```bash
git add run.bat
git commit -m "feat: add run.bat full run launcher"
```

---

## Task 10: End-to-end test run

This is the acceptance test for the full pipeline.

- [ ] **Step 1: Run in --test mode for both catalogs**

```
python save_session.py
python scrape_full.py --test
```

Expected:
- `save_session.py` exits with `auth.json saved`
- Phase 1 for `outdoor` prints product count from first load
- Phase 2 scrapes those products, prints `[N/N] products scraped`
- Phase 3 writes `dp_outdoor_full.csv`
- Validation runs (minor miss expected in test mode — only first load scraped)
- Same for `verticalgardens`
- No Python exceptions or `scrape_status: failed` rows

Open `dp_outdoor_full.csv` in Excel/Notepad and spot-check:
- `name` column has real product names
- `wholesale_price` has dollar values (confirms login is working)
- `image_1` has `https://` URLs
- `in_stock` has recognizable values (`In stock` / `Out of stock`)

- [ ] **Step 2: If wholesale_price is empty — fix auth**

If `wholesale_price` is empty for all rows, the session is either not being used or the selector is wrong. Debug steps:

```
python scrape_full.py --test --catalog outdoor --no-headless
```

Watch the browser. Navigate to a product page and inspect the `.price_custom` element in DevTools. If the element exists but has a different class, update the selector in `scrape_product()` at the `row["wholesale_price"]` line.

- [ ] **Step 3: Run verify.py**

```
python verify.py
```

Expected: `VERIFICATION PASSED — all checks green`

If coverage fails, re-run the affected catalog: `python scrape_full.py --catalog outdoor`

- [ ] **Step 4: Final commit**

```bash
git add dp_outdoor_full.csv dp_verticalgardens_full.csv
git commit -m "feat: initial scrape outputs — dp_outdoor and dp_verticalgardens"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ All 26 CSV fields defined in Task 4 and extracted in Task 6
- ✅ Load More pagination in Phase 1 (Task 5)
- ✅ Session refresh in save_session.py (Task 3)
- ✅ All 3 verify checks (Task 8)
- ✅ run.bat loops both catalogs + verify (Task 9)
- ✅ login.py + login.bat + setup.bat (Tasks 1–2)
- ✅ `--test`, `--no-headless`, `--concurrency`, `--catalog`, `--catalogs` CLI flags (Task 7)
- ✅ WooCommerce login field name ambiguity noted in Task 3 Step 1
- ✅ meta_description uses `get_attribute(..., "content")` not `textContent` (Task 6)

**Potential runtime issue flagged:** The `wait_for_url` lambda in `save_session.py` checks for `"orders" in url or "dashboard" in url` — WooCommerce may redirect to `/my-account/` (still contains `my-account`) after login. Task 3 Step 3 instructs the implementer to verify this and adjust if needed.
