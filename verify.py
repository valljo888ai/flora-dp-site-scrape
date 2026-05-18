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
import io
import sys

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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

CATALOGS = {
    "outdoor":         "/product-category/artificial-outdoor-plants/",
    "verticalgardens": "/product-category/vertical-garden-green-walls/",
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

CRITICAL_FIELDS = [
    "product_url", "sku", "name", "wholesale_price", "in_stock", "image_1",
]

KNOWN_STOCK_STATUSES = {"In stock", "Out of stock", "On backorder", "",
                        "In Stock", "Out of Stock"}  # site renders title-case


def canonical(href: str) -> str:
    return href.split("?")[0].rstrip("/")


async def crawl_category(page, cat_url: str, crawl_url: str | None = None) -> set[str]:
    """Re-crawl a category using /page/999/ redirect strategy. Returns set of canonical URLs.

    DP's category pages are cumulative: /page/N/ shows all products up to page N.
    /page/999/ redirects to the last real page, which contains every product in one shot.
    The Load More button uses Nitro CDN JS deferral (nitro-offscreen) and is unreliable
    in headless Playwright — the /page/999/ approach is the reliable alternative.

    For nested subcategory URLs where /page/999/ redirects to the parent, pass crawl_url
    pointing to a specific page that returns all products (see CRAWL_OVERRIDES).
    """
    if crawl_url:
        target = BASE_URL + crawl_url.rstrip("/") + "/"
    else:
        base = BASE_URL + cat_url.rstrip("/")
        target = base + "/page/999/"
    await page.goto(target, wait_until="networkidle", timeout=30_000)
    if "my-account" in page.url or "login" in page.url:
        raise RuntimeError("Session expired during verification — re-run save_session.py")

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
                site_urls = await crawl_category(page, cat_url, crawl_url=CRAWL_OVERRIDES.get(key))
                csv_urls  = {canonical(r["product_url"]) for r in csv_data[key]}
                # Load skipped URLs from sidecar file (broken listings that redirect to category)
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
