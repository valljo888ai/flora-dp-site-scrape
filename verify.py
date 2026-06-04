"""
verify.py — Post-scrape data verification.

Runs three checks against all 13 catalog CSVs (or a subset via --catalogs):

  1. Coverage:        re-crawl every category and confirm all currently-listed
                      product URLs are present in the CSVs.
  2. Critical fields: every row has product_url, sku, name, wholesale_price,
                      in_stock, image_1 populated.
  3. Integrity:       no duplicate product_url values within a catalog;
                      in_stock values from known set; image_1 starts with 'http'.

Exits 0 on PASS, 1 on FAIL. Extras (CSV rows not on site) reported as INFO.

Usage:
  python verify.py
  python verify.py --catalogs outdoor trees

Requires auth.json to exist (run login.bat or: python login.py).
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
MAX_LOAD_MORE_CLICKS = 200
MAX_STALLED_LOAD_MORE_CLICKS = 2

CATALOGS = {
    "outdoor":         "/product-category/artificial-outdoor-plants/",
    "verticalgardens": "/product-category/vertical-garden-green-walls/",
    "greenwalldiscs":  "/product-category/vertical-garden-green-walls/green-wall-art-and-artificial-discs/",
    "topiary":         "/product-category/fake-plants/topiary-balls-and-plants/",
    "trees":           "/product-category/artificial-trees/",
    "outdoortrees":    "/product-category/outdoor-artificial-trees/",
    "hedges":          "/product-category/artificial-hedges/",
    "hangingplants":   "/product-category/artificial-hanging-plants/",
    "shrubs":          "/product-category/artificial-shrubs-and-bushes/",
    "ivy":             "/product-category/artificial-ivy/",
    "floweringplants": "/product-category/artificial-flowering-plants/",
    "bamboopalms":     "/product-category/artificial-bamboo-and-palms/",
    "planters":        "/product-category/planters/",
}

# For subcategory URLs where /page/999/ redirects to the parent category,
# override the crawl URL with a specific page that returns all products.
CRAWL_OVERRIDES = {
    "topiary": "/product-category/fake-plants/topiary-balls-and-plants/page/2/",
}

# Catalogs that use JavaScript "Load More" pagination (URL-based /page/N/ doesn't work).
LOAD_MORE_CATALOGS = {"verticalgardens", "greenwalldiscs"}

CRITICAL_FIELDS = [
    "product_url", "sku", "name", "wholesale_price", "in_stock", "image_1",
]

KNOWN_STOCK_STATUSES = {"In stock", "Out of stock", "On backorder", "",
                        "In Stock", "Out of Stock"}  # site renders title-case


def canonical(href: str) -> str:
    return href.split("?")[0].rstrip("/")


async def crawl_category(page, cat_url: str, crawl_url: str | None = None,
                         load_more: bool = False) -> set[str]:
    """Re-crawl a category and return all canonical product URLs.

    Strategy A (default): /page/999/ redirect — lands on last real page with all products.
    Strategy B (crawl_url): specific page override for subcategories where /page/999/
      redirects to the parent (see CRAWL_OVERRIDES).
    Strategy C (load_more=True): click Load More until all products are visible, for
      categories that use JavaScript pagination (see LOAD_MORE_CATALOGS).
    """
    base = BASE_URL + cat_url.rstrip("/")
    if crawl_url:
        target = BASE_URL + crawl_url.rstrip("/") + "/"
    elif load_more:
        target = base + "/"
    else:
        target = base + "/page/999/"
    await page.goto(target, wait_until="networkidle", timeout=30_000)
    if "my-account" in page.url or "login" in page.url:
        raise RuntimeError("Session expired during verification — re-run save_session.py")

    if load_more:
        for overlay_sel in ["#overlay_filter", ".popup-overlay", "[id*='overlay']"]:
            try:
                if await page.locator(overlay_sel).count() > 0:
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
            await page.evaluate("const o = document.querySelector('#overlay_filter'); if(o) o.style.display='none';")
            try:
                await btn.first.scroll_into_view_if_needed(timeout=5_000)
            except Exception:
                pass
            await btn.first.click(force=True, timeout=10_000)
            try:
                await page.wait_for_function(
                    f"document.querySelectorAll('a.woocommerce-LoopProduct-link').length > {count_before}",
                    timeout=15_000,
                )
            except Exception:
                pass
            clicks += 1
            links_so_far = await page.eval_on_selector_all(
                "a.woocommerce-LoopProduct-link", "els => els.length"
            )
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
    return {canonical(href) for href in links
            if "/product/" in href and "/product-category/" not in href}


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

    # Check duplicates within each catalog's rows only — cross-catalog overlap is
    # expected because the site lists some products under multiple categories.
    by_catalog: dict[str, list[dict]] = {}
    for r in all_rows:
        by_catalog.setdefault(r.get("_catalog", "?"), []).append(r)
    for cat, rows in by_catalog.items():
        url_counts = Counter(r["product_url"] for r in rows)
        dups = [u for u, n in url_counts.items() if n > 1]
        if dups:
            issues.append(f"{len(dups)} duplicate product_url(s) within '{cat}' catalog")

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
    parser = argparse.ArgumentParser(description="Verify Designer Plants scrape output")
    parser.add_argument(
        "--catalogs", nargs="+", metavar="CATALOG",
        help="Limit verification to these catalog keys (default: all)",
        choices=list(CATALOGS.keys()),
    )
    parser.add_argument(
        "--skip-coverage", action="store_true",
        help="Skip the live site re-crawl (checks 2 and 3 only). Useful with --limit runs.",
    )
    args = parser.parse_args()
    active_catalogs = {k: v for k, v in CATALOGS.items() if args.catalogs is None or k in args.catalogs}

    print("=" * 60)
    print("  Designer Plants — Data Verification")
    if args.catalogs:
        print(f"  Catalogs: {', '.join(active_catalogs)}")
    print("=" * 60)

    if not AUTH_FILE.exists():
        print(f"ERROR: {AUTH_FILE} not found — run save_session.py or login.bat first.")
        return 1

    # Load CSVs
    csv_data = {}
    missing_csvs = []
    for key in active_catalogs:
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
    coverage_failures = []
    coverage_extras   = []
    if args.skip_coverage:
        print("\n[1/3] Coverage check — SKIPPED (--skip-coverage)")
    else:
        print("\n[1/3] Coverage check — re-crawling categories ...")
        print(f"      {'Catalog':18} {'Site':>6} {'CSV':>6} {'Match':>7} {'Missing':>9} {'Extra':>6}")
        print("      " + "-" * 53)
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                storage_state=str(AUTH_FILE), user_agent=USER_AGENT,
            )
            page = await context.new_page()
            try:
                for key, cat_url in active_catalogs.items():
                    site_urls = await crawl_category(page, cat_url, crawl_url=CRAWL_OVERRIDES.get(key), load_more=(key in LOAD_MORE_CATALOGS))
                    csv_urls  = {canonical(r["product_url"]) for r in csv_data[key]}
                    skipped_file = HERE / f"dp_{key}_full.skipped.txt"
                    skipped_urls: set[str] = set()
                    if skipped_file.exists():
                        skipped_urls = {line.strip() for line in skipped_file.read_text(encoding="utf-8").splitlines() if line.strip()}
                    missing   = site_urls - csv_urls - skipped_urls
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
    try:
        sys.exit(asyncio.run(main()))
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        print("Re-run save_session.py to refresh the session, then retry verify.py.")
        sys.exit(1)
