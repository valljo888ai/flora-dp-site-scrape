# flora-dp-site-scrape

Deterministic, session-authenticated Playwright scraper for the Designer Plants wholesale catalogue (`designerplants.com.au`). Produces one CSV per product category. Intended for downstream import into Shopify / n8n pipelines.

---

## Repository layout

```
flora-dp-site-scrape/
├── login.py            # Authenticate and save auth.json (interactive or --force)
├── scrape_full.py      # Main scraper — 3-phase, all 13 catalogs
├── verify.py           # Post-scrape data verification (coverage + field + integrity)
├── setup.bat           # One-time: pip install playwright + playwright install chromium
├── login.bat           # Wrapper: python login.py (interactive, first-time use)
├── run.bat             # Full run: login --force → scrape all → verify
├── test_e2e.bat        # Smoke test: 5 products from outdoor + --skip-coverage verify
├── auth.json           # (gitignored) Saved Playwright browser session
├── credentials.json    # (gitignored) {"email": "...", "password": "..."} for --force
├── dp_*_full.csv       # (gitignored) Scraped product data, one file per catalog
├── dp_*_full.skipped.txt  # (gitignored) Broken listing URLs excluded from coverage check
└── docs/
    └── superpowers/
        ├── plans/      # Implementation history
        └── specs/      # Original design spec
```

---

## Authentication

The site (`designerplants.com.au`) gates wholesale pricing behind a WooCommerce login. Playwright saves the browser's `storage_state` (cookies + localStorage) to `auth.json`. All subsequent scrape sessions load that file to skip login.

### login.py

Logs in headlessly and writes `auth.json`.

**Credential resolution order:**
1. Environment variables `DP_EMAIL` and `DP_PASSWORD`
2. `credentials.json` in the same directory: `{"email": "...", "password": "..."}`
3. Interactive prompt (only when `--force` is NOT set)

**Flags:**
- `python login.py` — interactive; prompts before overwriting existing `auth.json`
- `python login.py --force` — non-interactive; always overwrites; errors if no credentials found; used by `run.bat` and `test_e2e.bat`

**Session validity check:** after submitting the login form the script navigates to `/product-category/artificial-outdoor-plants/` and confirms the page URL does not redirect back to `/my-account/` or `/login/`.

---

## Catalogs

13 catalogs are defined in `scrape_full.py::CATALOGS`. Each entry contains:

| Key | `label` | `category_url` | `output` file | Special |
|---|---|---|---|---|
| `outdoor` | Outdoor Plants | `/product-category/artificial-outdoor-plants/` | `dp_outdoor_full.csv` | — |
| `verticalgardens` | Vertical Gardens | `/product-category/vertical-garden-green-walls/` | `dp_verticalgardens_full.csv` | `load_more: True` |
| `greenwalldiscs` | Green Wall Discs | `/product-category/vertical-garden-green-walls/green-wall-art-and-artificial-discs/` | `dp_greenwalldiscs_full.csv` | `load_more: True` |
| `topiary` | Topiary | `/product-category/fake-plants/topiary-balls-and-plants/` | `dp_topiary_full.csv` | `crawl_url` override |
| `trees` | Artificial Trees | `/product-category/artificial-trees/` | `dp_trees_full.csv` | — |
| `outdoortrees` | Outdoor Trees | `/product-category/outdoor-artificial-trees/` | `dp_outdoortrees_full.csv` | — |
| `hedges` | Hedges | `/product-category/artificial-hedges/` | `dp_hedges_full.csv` | — |
| `hangingplants` | Hanging Plants | `/product-category/artificial-hanging-plants/` | `dp_hangingplants_full.csv` | — |
| `shrubs` | Shrubs & Small Plants | `/product-category/artificial-shrubs-and-bushes/` | `dp_shrubs_full.csv` | — |
| `ivy` | Ivy & Garlands | `/product-category/artificial-ivy/` | `dp_ivy_full.csv` | — |
| `floweringplants` | Flowering Plants | `/product-category/artificial-flowering-plants/` | `dp_floweringplants_full.csv` | — |
| `bamboopalms` | Bamboos & Palms | `/product-category/artificial-bamboo-and-palms/` | `dp_bamboopalms_full.csv` | — |
| `planters` | Planters | `/product-category/planters/` | `dp_planters_full.csv` | — |

---

## Scraper architecture — scrape_full.py

Each catalog runs through three sequential phases inside `run_catalog_async()`.

### Phase 1 — Category crawl

Collects all product URLs for the catalog. Returns a deduplicated Python `set[str]`.

Three pagination strategies, selected per-catalog:

**Strategy A — `/page/999/` redirect (default)**
WooCommerce cumulative pages: requesting page 999 of a paginated category redirects to the actual last page, which renders all products on a single HTML page. All `a.woocommerce-LoopProduct-link` hrefs are extracted in one pass.

**Strategy B — `crawl_url` override**
Used for nested subcategory URLs (e.g. `topiary`) where `/page/999/` redirects to the parent category rather than the last page of the subcategory. A specific known-good page URL is configured in `CATALOGS[key]["crawl_url"]`.

**Strategy C — Load More (`load_more: True`)**
Used for `verticalgardens` and `greenwalldiscs`, which use JavaScript pagination. The scraper clicks `button.load-more-button-new` repeatedly until it disappears. Safety limits: `MAX_LOAD_MORE_CLICKS = 200`, `MAX_STALLED_LOAD_MORE_CLICKS = 2` (stops if two consecutive clicks add no new products). An overlay element (`#overlay_filter`) is removed via JavaScript before each click to prevent it blocking the button.

**test_mode:** when `--test` is passed, all strategies fall back to loading the base category URL only (~20 products, first page).

**`--limit N`:** after phase 1 completes, the URL list is sliced to N before phase 2 runs. Does not affect the crawl itself.

### Phase 2 — Product scrape

`phase2_scrape()` visits each URL in the phase 1 set using `asyncio` with `--concurrency` (default 3) Playwright pages open in parallel.

For each product URL, `scrape_product()`:
1. Navigates to the URL with `wait_until="domcontentloaded"`, timeout 30s
2. **Broken listing detection (redirect to category):** if `page.url` contains `/product-category/`, marks `scrape_status = "skipped"` and returns immediately
3. **Broken listing detection (redirect to different product):** if `canonical_url(page.url) != canonical_url(input_url)`, marks `scrape_status = "skipped"` and returns. This catches products whose slug silently redirects to a completely different product page on the site.
4. Waits for `h1` selector to confirm full page load
5. Extracts all 26 fields (see CSV schema below)
6. `product_url` is always set to the **original input URL** (the URL that appeared in the category listing), not the page URL after Playwright navigation

**Retry logic:** after all products are scraped, any rows with `scrape_status = "failed"` are retried once.

**Session expiry:** if any navigation redirects to `/my-account/` or `/login/`, a `SessionExpiredError` is raised and the entire catalog run aborts with exit code 1.

### Phase 3 — CSV assembly + inline validation

1. Rows with `scrape_status = "skipped"` are separated and their canonical URLs written to `dp_<catalog>_full.skipped.txt`
2. Remaining rows are written to `dp_<catalog>_full.csv` via `csv.DictWriter`
3. **Inline validation** re-crawls the category (same phase 1 logic) and compares found URLs against the CSV. Reports missing/extra. Wrapped in `try/except` — a timeout here prints a warning but does not abort remaining catalogs.

---

## CSV schema

Every output CSV has exactly these 26 columns:

| Column | Description |
|---|---|
| `category` | Catalog label string (e.g. `"Outdoor Plants"`) |
| `product_url` | Canonical product URL as it appeared in the category listing |
| `product_id` | URL slug extracted from `product_url` (e.g. `"artificial-ficus-tree-180cm"`) |
| `sku` | Digits-only SKU from `p.product-sku` |
| `name` | Product title from `h1` |
| `in_stock` | Stock status string: `"In Stock"`, `"Out of Stock"`, `"On backorder"`, or `""` |
| `breadcrumb` | Full breadcrumb trail as a single string |
| `short_description` | WooCommerce short description HTML (stripped) |
| `description` | Long description HTML (stripped) |
| `sale_price` | Active sale price; empty if not on sale |
| `regular_price` | Regular (non-sale) price |
| `retail_price` | RRP / retail price if shown separately |
| `wholesale_price` | Wholesale price (the primary price for this login context) |
| `save_amount` | Calculated saving amount if shown |
| `variable_price_range` | Price range string for variable products (e.g. `"$12.00 – $45.00"`) |
| `rating` | Average star rating (float string) |
| `review_count` | Number of reviews (integer string) |
| `seo_title` | `<title>` tag content |
| `meta_description` | `<meta name="description">` content |
| `image_1` … `image_5` | Absolute URLs of product gallery images (up to 5) |
| `scraped_at` | ISO 8601 UTC timestamp of when the row was scraped |
| `scrape_status` | `"ok"` for all rows written to CSV (`"skipped"` rows are excluded) |

**Note:** products that appear in multiple category listings will have separate rows in each catalog's CSV with different `category` values but the same `product_url`.

---

## Sidecar skipped files

Each catalog produces `dp_<catalog>_full.skipped.txt` alongside its CSV. Each line is a canonical product URL that was found in the category listing but excluded from the CSV because the page redirected to a category or to a different product. `verify.py` reads these files and excludes those URLs from the coverage missing-check, preventing false failures.

---

## verify.py

Post-scrape verification tool. Loads all 13 CSVs and runs three checks.

**Check 1 — Coverage** (skipped with `--skip-coverage`):
Re-crawls every category using the same phase 1 logic. For each catalog compares site URLs against CSV `product_url` values, excluding entries in the catalog's `.skipped.txt`. Reports missing (in site but not in CSV) and extra (in CSV but not on site — de-listed since scrape, reported as INFO only, not a failure).

**Check 2 — Critical fields:**
Every row must have non-empty values for: `product_url`, `sku`, `name`, `wholesale_price`, `in_stock`, `image_1`.

**Check 3 — Integrity:**
- No duplicate `product_url` values within a single catalog's rows
- `in_stock` value is in the known set: `{"In Stock", "Out of Stock", "On backorder", "", "In Stock", "Out of Stock"}`
- `image_1` starts with `"http"` where populated

**Flags:**
- `--catalogs outdoor trees` — limit to specific catalog keys
- `--skip-coverage` — skip check 1 (no browser needed; use after `--limit` runs or for field/integrity-only checks)

**Exit codes:** 0 = all checks passed, 1 = any check failed or missing CSV.

---

## CLI reference

```
# One-time setup
setup.bat

# Save session (first time or refresh)
python login.py                          # interactive
python login.py --force                  # non-interactive (uses env vars or credentials.json)

# Scrape
python scrape_full.py                    # all 13 catalogs
python scrape_full.py --catalog outdoor  # single catalog
python scrape_full.py --catalogs "outdoor,trees,shrubs"  # subset
python scrape_full.py --test             # first page only per catalog (~20 products)
python scrape_full.py --limit 5          # cap products per catalog after phase 1
python scrape_full.py --concurrency 5   # parallel pages in phase 2 (default: 3)
python scrape_full.py --no-headless      # show browser window

# Verify
python verify.py                         # all 13 catalogs, full checks
python verify.py --catalogs outdoor      # single catalog
python verify.py --skip-coverage         # fields + integrity only, no re-crawl

# Launchers
run.bat                                  # login --force + scrape all + verify
run.bat --catalog outdoor                # login --force + single catalog (no verify)
test_e2e.bat                             # login + 5 products from outdoor + --skip-coverage verify
```

---

## Execution flow — run.bat

`run.bat` is the production entry point for full runs:

```
for each catalog in (outdoor verticalgardens ... planters):
    python login.py --force      ← refresh session before each catalog
    python scrape_full.py --catalog <key> --concurrency 3

python login.py --force          ← refresh session before verify
python verify.py
```

Session is refreshed before every catalog (not just once at the start) because a full run takes 45–90 minutes and WooCommerce sessions expire.

---

## Known site behaviours and edge cases

**Broken product listings — category redirect:**
Some product URLs in category listings redirect to a category page instead of a product. Detected by checking `"/product-category/" in page.url` after navigation. Marked `scrape_status = "skipped"`, URL written to `.skipped.txt`. Example: `garden-of-eden-bespoke-vertical-garden-green-wall-uv-resistant` (outdoor catalog).

**Broken product listings — product-to-product redirect:**
Some product slugs redirect to a completely different product page. Detected by `canonical_url(page.url) != canonical_url(input_url)`. Marked as skipped. Example: `pothospoletree`, `faux-natural-fern-tree-90cm`, `artificial-bushy-olive-tree-olives-180cm` all redirect to `artificial-potted-150cm-bird-of-paradise-plant` (a since-de-listed product).

**De-listed products:**
Products removed from the site after scraping appear as "Extra" in verify.py's coverage check. This is expected and reported as INFO, not a failure.

**Load More stalling:**
`verticalgardens` and `greenwalldiscs` occasionally have a Load More click that loads 0 new products (site bug). The scraper allows up to `MAX_STALLED_LOAD_MORE_CLICKS = 2` consecutive stalls before stopping.

**`topiary` pagination override:**
`/product-category/fake-plants/topiary-balls-and-plants/page/999/` redirects to the parent category, not the last topiary page. The `crawl_url` override uses `/page/2/` which contains all topiary products.

**Products appearing in multiple catalogs:**
Several products are listed under multiple categories on the site. Each catalog CSV will contain its own row for that product, with a different `category` value. `verify.py` checks for duplicates within each catalog's rows only, not across catalogs.

**Navigation timeouts:**
`page.goto()` uses `wait_until="networkidle"` with a 60-second timeout. A session that has been active for a long time may be slow; the 60s limit was increased from 30s after observing timeouts after 11-minute scrape sessions.

---

## Dependencies

```
pip install playwright
python -m playwright install chromium
```

Python 3.10+ required (uses `str | None` union syntax). Tested on Python 3.14.

All scripts include a Windows-specific stdout encoding fix at the top:
```python
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
```
This is required because the default Windows console code page (cp1252) cannot encode Unicode arrow characters and other symbols used in print output.

---

## Gitignore policy

| Pattern | Reason |
|---|---|
| `auth.json` | Session credentials — never commit |
| `credentials.json` | Login credentials — never commit |
| `dp_*.csv` | Runtime scrape output — large, regenerated on each run |
| `dp_*.skipped.txt` | Runtime sidecar output |
| `__pycache__/`, `*.pyc` | Python bytecode |
| `.venv/`, `venv/` | Virtual environments |
| `.playwright-mcp/` | Playwright MCP artifacts |

---

## Typical run metrics (June 2026 baseline)

| Catalog | Products | Skipped | Time (phase 2) |
|---|---|---|---|
| outdoor | 199 | 1 | ~11 min |
| verticalgardens | 154 | 1 | ~8 min |
| greenwalldiscs | 56 | 0 | ~3 min |
| topiary | 32 | 0 | ~1 min |
| trees | 80 | 0 | ~3 min |
| outdoortrees | 37 | 0 | ~1 min |
| hedges | 18 | 0 | ~1 min |
| hangingplants | 106 | 0 | ~4 min |
| shrubs | 88 | 0 | ~3 min |
| ivy | 67 | 0 | ~2 min |
| floweringplants | 52 | 0 | ~2 min |
| bamboopalms | 20 | 0 | ~1 min |
| planters | 51 | 0 | ~1 min |
| **Total** | **960** | **2** | **~45 min** |

Concurrency default is 3 pages in parallel. Increasing `--concurrency` reduces phase 2 time proportionally up to the site's rate limit tolerance (tested stable at 3; 5 untested in production).
