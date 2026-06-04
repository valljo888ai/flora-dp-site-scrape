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
  outdoor | verticalgardens | greenwalldiscs | topiary | trees | outdoortrees | hedges |
  hangingplants | shrubs | ivy | floweringplants | bamboopalms | planters
"""

import io
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import argparse
import asyncio
import csv
import pathlib
import re
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
MAX_LOAD_MORE_CLICKS = 200
MAX_STALLED_LOAD_MORE_CLICKS = 2

# ── Catalog definitions ────────────────────────────────────────────────────────
CATALOGS = {
    "outdoor":        {"label": "Outdoor Plants",        "category_url": "/product-category/artificial-outdoor-plants/",            "output": HERE / "dp_outdoor_full.csv"},
    "verticalgardens":{"label": "Vertical Gardens",      "category_url": "/product-category/vertical-garden-green-walls/",          "output": HERE / "dp_verticalgardens_full.csv",  "load_more": True},
    "greenwalldiscs": {"label": "Green Wall Discs",     "category_url": "/product-category/vertical-garden-green-walls/green-wall-art-and-artificial-discs/", "output": HERE / "dp_greenwalldiscs_full.csv", "load_more": True},
    "topiary":        {"label": "Topiary",               "category_url": "/product-category/fake-plants/topiary-balls-and-plants/", "output": HERE / "dp_topiary_full.csv", "crawl_url": "/product-category/fake-plants/topiary-balls-and-plants/page/2/"},
    "trees":          {"label": "Artificial Trees",      "category_url": "/product-category/artificial-trees/",                     "output": HERE / "dp_trees_full.csv"},
    "outdoortrees":   {"label": "Outdoor Trees",         "category_url": "/product-category/outdoor-artificial-trees/",             "output": HERE / "dp_outdoortrees_full.csv"},
    "hedges":         {"label": "Hedges",                "category_url": "/product-category/artificial-hedges/",                    "output": HERE / "dp_hedges_full.csv"},
    "hangingplants":  {"label": "Hanging Plants",        "category_url": "/product-category/artificial-hanging-plants/",            "output": HERE / "dp_hangingplants_full.csv"},
    "shrubs":         {"label": "Shrubs & Small Plants", "category_url": "/product-category/artificial-shrubs-and-bushes/",         "output": HERE / "dp_shrubs_full.csv"},
    "ivy":            {"label": "Ivy & Garlands",        "category_url": "/product-category/artificial-ivy/",                      "output": HERE / "dp_ivy_full.csv"},
    "floweringplants":{"label": "Flowering Plants",      "category_url": "/product-category/artificial-flowering-plants/",          "output": HERE / "dp_floweringplants_full.csv"},
    "bamboopalms":    {"label": "Bamboos & Palms",       "category_url": "/product-category/artificial-bamboo-and-palms/",          "output": HERE / "dp_bamboopalms_full.csv"},
    "planters":       {"label": "Planters",              "category_url": "/product-category/planters/",                            "output": HERE / "dp_planters_full.csv"},
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


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — Category crawl
# ═══════════════════════════════════════════════════════════════════════════════

async def phase1_crawl(page, category_url: str, test_mode: bool = False,
                       crawl_url: str | None = None, load_more: bool = False) -> list[str]:
    """
    Collect all product URLs for a category.

    Strategy A (default): /page/999/ redirect — WooCommerce cumulative pages redirect
      to the last real page which contains every product in one shot.

    Strategy B (crawl_url): for nested subcategory URLs where /page/999/ redirects to
      the parent, pass crawl_url pointing to a specific page that returns all products.

    Strategy C (load_more=True): for categories that use JavaScript "Load More" buttons
      and don't support URL-based pagination (e.g. verticalgardens, greenwalldiscs).
      Repeatedly clicks the Load More button until it disappears.

    In test_mode, loads only the first page (~20 products) regardless of strategy.

    Raises SessionExpiredError if redirected to login.
    """
    base = BASE_URL + category_url.rstrip("/")
    if test_mode:
        target = base
    elif crawl_url:
        target = BASE_URL + crawl_url.rstrip("/") + "/"
    elif load_more:
        target = base + "/"
    else:
        target = base + "/page/999/"

    await page.goto(target, wait_until="networkidle", timeout=60_000)

    if "my-account" in page.url or "login" in page.url:
        raise SessionExpiredError(
            "Session expired — re-run login.bat to refresh your auth.json"
        )

    # Strategy C: click Load More until gone
    if load_more and not test_mode:
        # Dismiss any overlay/popup that might intercept clicks
        for overlay_sel in ["#overlay_filter", ".popup-overlay", ".cookie-notice", "[id*='overlay']"]:
            try:
                overlay = page.locator(overlay_sel)
                if await overlay.count() > 0:
                    await page.evaluate(f"document.querySelector('{overlay_sel}').remove()")
            except Exception:
                pass

        clicks = 0
        stalled_clicks = 0
        while True:
            btn = page.locator("button.load-more-button-new")
            if await btn.count() == 0:
                break
            if clicks >= MAX_LOAD_MORE_CLICKS:
                print(f"    Stopping Load More after {clicks} clicks (safety limit)")
                break
            try:
                if not await btn.first.is_visible(timeout=2_000):
                    break
            except Exception:
                break
            count_before = await page.eval_on_selector_all(
                "a.woocommerce-LoopProduct-link", "els => els.length"
            )
            # Remove any overlay that might have reappeared
            await page.evaluate("const o = document.querySelector('#overlay_filter'); if(o) o.style.display='none';")
            try:
                await btn.first.scroll_into_view_if_needed(timeout=5_000)
            except Exception:
                pass  # Button may be detached (last page rendered) — check count on next iteration
            await btn.first.click(force=True, timeout=10_000)
            # Wait for new products to appear (count increases) rather than networkidle
            try:
                await page.wait_for_function(
                    f"document.querySelectorAll('a.woocommerce-LoopProduct-link').length > {count_before}",
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:
                pass  # Button may have disappeared (last page) — check on next loop iteration
            clicks += 1
            links_so_far = await page.eval_on_selector_all(
                "a.woocommerce-LoopProduct-link", "els => els.length"
            )
            print(f"    Load More click {clicks}: {links_so_far} products loaded so far")
            if links_so_far <= count_before:
                stalled_clicks += 1
                print(f"    Load More did not add products ({stalled_clicks}/{MAX_STALLED_LOAD_MORE_CLICKS})")
                if stalled_clicks >= MAX_STALLED_LOAD_MORE_CLICKS:
                    print("    Stopping Load More because product count stopped changing")
                    break
            else:
                stalled_clicks = 0

    links = await page.eval_on_selector_all(
        "a.woocommerce-LoopProduct-link",
        "els => els.map(el => el.href)"
    )
    urls = list(dict.fromkeys(
        canonical_url(h) for h in links
        if "/product/" in h and "/product-category/" not in h
    ))
    strategy = "Load More" if (load_more and not test_mode) else ("Test load" if test_mode else "Full load")
    print(f"  {strategy}: {len(urls)} products (landed on {page.url.split('designerplants.com.au')[-1]})")
    return urls


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

        # Guard: broken listing redirected to a category page
        if "/product-category/" in page.url:
            row["scrape_status"] = "skipped"
            return row

        # Guard: broken listing redirected to a completely different product page
        # (e.g. pothospoletree → bird-of-paradise). canonical_url strips trailing
        # slashes/query params so minor URL variations don't trigger a false skip.
        if canonical_url(page.url) != canonical_url(url):
            row["scrape_status"] = "skipped"
            return row

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

        # Always use the original input URL — it matches what the category page linked to
        # and what verify.py checks against. Canonical tag is not used for product_url.
        row["product_url"] = url

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


async def validate(page, category_url: str, scraped_urls: list[str],
                   skipped_urls: set[str] | None = None,
                   crawl_url: str | None = None,
                   load_more: bool = False) -> bool:
    """
    Re-crawl the category and assert every URL found appears in scraped_urls.
    skipped_urls are broken listings (redirected to category) — excluded from missing check.
    """
    print("\n-- Validation --")
    expected = await phase1_crawl(page, category_url, test_mode=False, crawl_url=crawl_url, load_more=load_more)
    scraped  = set(scraped_urls)
    excluded = skipped_urls or set()
    missing  = [u for u in expected if u not in scraped and u not in excluded]

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


# ═══════════════════════════════════════════════════════════════════════════════
# Per-catalog runner
# ═══════════════════════════════════════════════════════════════════════════════

async def run_catalog_async(catalog_key: str, catalog_config: dict, args) -> None:
    label        = catalog_config["label"]
    category_url = catalog_config["category_url"]
    output_csv   = catalog_config["output"]
    crawl_url    = catalog_config.get("crawl_url")
    load_more    = catalog_config.get("load_more", False)

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
            urls = await phase1_crawl(nav_page, category_url, test_mode=args.test, crawl_url=crawl_url, load_more=load_more)
        except SessionExpiredError as e:
            print(f"\nERROR: {e}")
            await browser.close()
            sys.exit(1)
        print(f"Phase 1 done in {time.time()-t1:.1f}s  —  {len(urls)} products")
        if args.limit and len(urls) > args.limit:
            urls = urls[:args.limit]
            print(f"  (--limit {args.limit}: capped to {len(urls)} products)")

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
        # Exclude broken listings that redirected to a category page
        skipped = [r for r in rows if r.get("scrape_status") == "skipped"]
        if skipped:
            print(f"  Skipped {len(skipped)} broken listing(s) (redirect to category page):")
            for r in skipped:
                print(f"    {r['product_url']}")
        rows = [r for r in rows if r.get("scrape_status") != "skipped"]
        phase3_write_csv(rows, output_csv)
        # Write skipped URLs to sidecar so verify.py can exclude them
        skipped_file = output_csv.with_suffix(".skipped.txt")
        with open(skipped_file, "w", encoding="utf-8") as f:
            for r in skipped:
                f.write(canonical_url(r["product_url"]) + "\n")

        # ── Validation ────────────────────────────────────────────────────────
        # Normalize scraped URLs the same way phase1_crawl normalizes them
        scraped_urls = [canonical_url(r["product_url"]) for r in rows if r["product_url"]]
        skipped_set  = {canonical_url(r["product_url"]) for r in skipped if r["product_url"]}
        try:
            await validate(nav_page, category_url, scraped_urls, skipped_urls=skipped_set, crawl_url=crawl_url, load_more=load_more)
        except Exception as e:
            print(f"\n  WARNING: inline validation failed ({e.__class__.__name__}: {e})")
            print("  CSV was written — run verify.py after all catalogs to check coverage.")

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
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the number of products scraped per catalog (useful for quick smoke tests).",
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
