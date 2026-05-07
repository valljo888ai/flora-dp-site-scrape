# FLORA DP Site Scrape — Design Spec
**Date:** 2026-05-07
**Status:** Approved

---

## Overview

A deterministic Playwright scraper for designerplants.com.au that exports all products from 2 categories to individual CSV files. Modelled identically on the FLORA FI Site Scrape project — same file structure, same 3-phase pipeline, same bat launchers, same verify step. The primary structural difference from FI is pagination: DP uses a "Load More" button rather than page-number URLs.

---

## Target Site

- **URL:** https://designerplants.com.au
- **Platform:** WooCommerce (WordPress)
- **Auth:** Login required to see wholesale prices. Credentials stored in `save_session.py`.
- **Categories scraped:** 2

---

## File Structure

```
FLORA DP Site Scrape/
├── setup.bat              ← Run once: installs playwright + chromium
├── login.bat              ← Run once (or on session expiry): manual browser login
├── run.bat                ← Run any time for a fresh scrape
│
├── scrape_full.py         ← Pipeline engine (primary edit target)
├── verify.py              ← Post-scrape verification (run automatically by run.bat)
├── login.py               ← Manual login → saves auth.json
├── save_session.py        ← Headless auto-login (used by run.bat before each catalog)
│
├── auth.json              ← Saved session (created by login.bat / save_session.py)
│
├── dp_outdoor_full.csv
└── dp_verticalgardens_full.csv
```

---

## Catalogs

Run in this order (reorder after first run once sizes are known):

| Key | Label | Category URL | Output |
|---|---|---|---|
| `outdoor` | Outdoor Plants | `/product-category/artificial-outdoor-plants/` | `dp_outdoor_full.csv` |
| `verticalgardens` | Vertical Gardens | `/product-category/vertical-garden-green-walls/` | `dp_verticalgardens_full.csv` |

---

## Phase Architecture

### Phase 1 — Load More crawl (replaces FI's page-number pagination)

DP uses a "Load More" button (`button.load-more-button-new`) rather than paginated URLs. Phase 1 must:

1. Navigate to the category URL with auth session
2. Collect all visible `a.woocommerce-LoopProduct-link` hrefs
3. If `button.load-more-button-new` exists and is visible, click it and wait for new products to render
4. Repeat until the button is gone or no new URLs are added
5. Deduplicate and return canonical product URLs

Session expiry check: if the page redirects to a login URL, raise `SessionExpiredError`.

### Phase 2 — Parallel product scrape

Same pattern as FI:
- `asyncio.Semaphore(3)` concurrency (reliability-first default)
- `scrape_product()` extracts all fields per page
- Render gate: `page.wait_for_selector("h1", timeout=30000)` — confirms page is loaded
- Automatic single-pass retry of any `scrape_status == "failed"` rows
- `--concurrency N` CLI flag (default 3, bump to 5/10 for speed)

### Phase 3 — CSV assembly + validation

- `csv.DictWriter` writes one CSV per catalog
- Post-write: re-crawl the category (Phase 1 logic) and assert all found URLs are present in the CSV

---

## Key Constants

```python
BASE_URL   = "https://designerplants.com.au"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."
AUTH_FILE  = HERE / "auth.json"
LOGIN_URL  = "https://designerplants.com.au/my-account/"
EMAIL      = "floradesigns.com.au"
PASSWORD   = "rfvEhnn9kc#O"
```

---

## CSV Field Reference (26 columns)

| Column | Selector / Source | Notes |
|---|---|---|
| `category` | Catalog config | e.g. `"Outdoor Plants"` |
| `product_url` | `link[rel='canonical']` | Canonical URL |
| `product_id` | Parsed from URL | WooCommerce slug or `?p=` param — resolved at runtime |
| `sku` | `p.product-sku` | Digits only (regex: `[0-9]+`) |
| `name` | `h1` | Product display name |
| `in_stock` | `p.stock-status` | e.g. `"In stock"`, `"Out of stock"` |
| `breadcrumb` | `.woocommerce-breadcrumb` | Full breadcrumb text |
| `short_description` | `.woocommerce-product-details__short-description` | Short product blurb |
| `description` | `.single_description_acc div.open` | Full description (accordion) |
| `sale_price` | `.mainsale-price .sale-price .woocommerce-Price-amount bdi` | Discounted price |
| `regular_price` | `.mainsale-price .regular-price .woocommerce-Price-amount bdi` | Standard listed price |
| `retail_price` | `p.price.no-sale .woocommerce-Price-amount bdi` | RRP (no sale active) |
| `wholesale_price` | `.price_custom .woocommerce-Price-amount bdi` | Trade price (auth-gated) |
| `save_amount` | `.saveprice .woocommerce-Price-amount bdi` | Saving vs retail |
| `variable_price_range` | `.variations_form ~ * .price, .single_variation_wrap .price` | Variable product range |
| `rating` | `.star-rating` | Float, regex `[0-9]+\.[0-9]+` |
| `review_count` | `.woocommerce-review-link` | Integer, regex `[0-9]+` |
| `seo_title` | `title` | Page `<title>` tag |
| `meta_description` | `meta[property='og:description']` content attr | OG description |
| `image_1` | `.wpgs-for img[data-large_image]` nth=0 | `data-large_image` attr |
| `image_2` | `.wpgs-for img[data-large_image]` nth=1 | Empty if fewer than 2 images |
| `image_3` | `.wpgs-for img[data-large_image]` nth=2 | Empty if fewer than 3 images |
| `image_4` | `.wpgs-for img[data-large_image]` nth=3 | Empty if fewer than 4 images |
| `image_5` | `.wpgs-for img[data-large_image]` nth=4 | Empty if fewer than 5 images |
| `scraped_at` | Script runtime | ISO 8601 UTC |
| `scrape_status` | Internal | `"ok"` or `"failed"` |

---

## Verify Checks

Three checks, same structure as FI:

1. **Coverage** — re-crawl both categories using Load More logic, confirm every found URL has a row in the corresponding CSV
2. **Critical fields** — every row must have `product_url`, `sku`, `name`, `wholesale_price`, `in_stock`, `image_1` populated
3. **Integrity** — no duplicate `product_url` values across CSVs; `in_stock` values from known set; `image_1` looks like a real URL (starts with `http`)

Exits 0 on PASS, 1 on FAIL. Extras (rows in CSV not found on site) reported as INFO, not failure.

---

## run.bat Behaviour

```
1. For each catalog (outdoor → verticalgardens):
   a. python save_session.py      ← headless login refresh
   b. python scrape_full.py --catalog <key> --concurrency 3
2. python save_session.py         ← refresh before verify
3. python verify.py
```

Exits non-zero on any failure. All args passed through to `scrape_full.py` (e.g. `run.bat --test`).

---

## CLI Options (scrape_full.py)

```
--catalog KEY       outdoor|verticalgardens|all  (default: all)
--catalogs LIST     Comma-separated keys, e.g. --catalogs outdoor,verticalgardens
--test              First page / first load of each catalog only (~1 min)
--no-headless       Show browser window (debug)
--concurrency N     Playwright tabs in parallel (default: 3)
```

---

## save_session.py Behaviour

1. Launch headless Chromium
2. Navigate to `LOGIN_URL`
3. Fill `input[name="username"]` (or `input[name="email"]`) and `input[name="password"]`
4. Submit form
5. Wait for redirect away from login URL
6. Verify session by navigating to a category page — if redirected back to login, exit with error
7. Save `context.storage_state()` to `auth.json`

---

## Implementation Notes

**Load More pagination:** After each click, wait for the network to settle (`wait_for_load_state("networkidle")` or a short `asyncio.sleep`) before re-collecting links. Guard against infinite loops: if a click produces no new URLs, stop.

**WooCommerce product ID:** WooCommerce canonical URLs are typically `/product/slug/`. Extract ID from `?p=N` if available in the page source, or use the slug as the identifier. Confirm approach by inspecting a live product page during implementation.

**`meta_description` extraction:** Use `page.get_attribute('meta[property="og:description"]', 'content')` rather than `textContent`.

**WooCommerce login field name:** The username field may be `input[name="username"]` or `input[name="email"]` depending on site config. During implementation, inspect the live login page and use whichever is present. The credential value `floradesigns.com.au` is a username, not an email address.

**User agent required:** Pass `USER_AGENT` to every `browser.new_context()` call to avoid bot detection.

**Session check:** After `page.goto()` in Phase 1, check if the URL contains `/my-account/` or `/login` → raise `SessionExpiredError`.

---

## Dependencies

Same as FI:

| Package | Purpose |
|---|---|
| `playwright` | All scraping and login |
| Chromium | Via `playwright install chromium` |

Python 3.10+ required.
