# DP Scraper — Expand to 12 Catalogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Designer Plants scraper from 2 catalogs to 12, covering all product categories that Flora sells, so the FLORA SKU pipeline stops generating false-positive discontinuation flags for active DP products.

**Architecture:** Three files contain hardcoded catalog definitions — `scrape_full.py` (CATALOGS dict, scrape engine), `verify.py` (CATALOGS dict, verification), and `run.bat` (loop over catalog keys). All three must be updated consistently. No new files, no new logic — only catalog entries and the loop in run.bat. The pipeline's Phase 1 already deduplicates on `SOH SKU` (keep first), so cross-catalog product overlaps in the CSVs are harmless.

**Tech Stack:** Python 3.10+, Playwright (async), csv (stdlib), asyncio (stdlib), Windows batch

---

## File Map

| File | Action | What changes |
|---|---|---|
| `scrape_full.py` | Modify | Expand `CATALOGS` dict from 2 to 12 entries |
| `verify.py` | Modify | Expand `CATALOGS` dict from 2 to 12 entries (same keys + URLs) |
| `run.bat` | Modify | Update `for %%C in (...)` loop to include all 12 catalog keys |

No new files. No logic changes. No test files needed — correctness is validated by the existing `verify.py` coverage check, which re-crawls each category after scraping.

---

## New Catalogs Being Added

| Key | Label | Category URL | Output CSV |
|---|---|---|---|
| `topiary` | Topiary | `/product-category/fake-plants/topiary-balls-and-plants/` | `dp_topiary_full.csv` |
| `trees` | Artificial Trees | `/product-category/artificial-trees/` | `dp_trees_full.csv` |
| `outdoortrees` | Outdoor Trees | `/product-category/outdoor-artificial-trees/` | `dp_outdoortrees_full.csv` |
| `hedges` | Hedges | `/product-category/artificial-hedges/` | `dp_hedges_full.csv` |
| `hangingplants` | Hanging Plants | `/product-category/artificial-hanging-plants/` | `dp_hangingplants_full.csv` |
| `shrubs` | Shrubs & Small Plants | `/product-category/artificial-shrubs-and-bushes/` | `dp_shrubs_full.csv` |
| `ivy` | Ivy & Garlands | `/product-category/artificial-ivy/` | `dp_ivy_full.csv` |
| `floweringplants` | Flowering Plants | `/product-category/artificial-flowering-plants/` | `dp_floweringplants_full.csv` |
| `bamboopalms` | Bamboos & Palms | `/product-category/artificial-bamboo-and-palms/` | `dp_bamboopalms_full.csv` |
| `planters` | Planters | `/product-category/planters/` | `dp_planters_full.csv` |

Existing catalogs retained unchanged:
- `outdoor` → `/product-category/artificial-outdoor-plants/` → `dp_outdoor_full.csv`
- `verticalgardens` → `/product-category/vertical-garden-green-walls/` → `dp_verticalgardens_full.csv`

---

## Task 1: Expand CATALOGS in scrape_full.py

**Files:**
- Modify: `scrape_full.py` lines 54–57

- [ ] **Step 1: Open scrape_full.py and replace the CATALOGS dict**

Find this block (lines 54–57):

```python
CATALOGS = {
    "outdoor":        {"label": "Outdoor Plants",   "category_url": "/product-category/artificial-outdoor-plants/",  "output": HERE / "dp_outdoor_full.csv"},
    "verticalgardens": {"label": "Vertical Gardens", "category_url": "/product-category/vertical-garden-green-walls/", "output": HERE / "dp_verticalgardens_full.csv"},
}
```

Replace with:

```python
CATALOGS = {
    "outdoor":        {"label": "Outdoor Plants",      "category_url": "/product-category/artificial-outdoor-plants/",             "output": HERE / "dp_outdoor_full.csv"},
    "verticalgardens":{"label": "Vertical Gardens",    "category_url": "/product-category/vertical-garden-green-walls/",           "output": HERE / "dp_verticalgardens_full.csv"},
    "topiary":        {"label": "Topiary",             "category_url": "/product-category/fake-plants/topiary-balls-and-plants/",  "output": HERE / "dp_topiary_full.csv"},
    "trees":          {"label": "Artificial Trees",    "category_url": "/product-category/artificial-trees/",                      "output": HERE / "dp_trees_full.csv"},
    "outdoortrees":   {"label": "Outdoor Trees",       "category_url": "/product-category/outdoor-artificial-trees/",              "output": HERE / "dp_outdoortrees_full.csv"},
    "hedges":         {"label": "Hedges",              "category_url": "/product-category/artificial-hedges/",                     "output": HERE / "dp_hedges_full.csv"},
    "hangingplants":  {"label": "Hanging Plants",      "category_url": "/product-category/artificial-hanging-plants/",             "output": HERE / "dp_hangingplants_full.csv"},
    "shrubs":         {"label": "Shrubs & Small Plants","category_url": "/product-category/artificial-shrubs-and-bushes/",         "output": HERE / "dp_shrubs_full.csv"},
    "ivy":            {"label": "Ivy & Garlands",      "category_url": "/product-category/artificial-ivy/",                       "output": HERE / "dp_ivy_full.csv"},
    "floweringplants":{"label": "Flowering Plants",    "category_url": "/product-category/artificial-flowering-plants/",           "output": HERE / "dp_floweringplants_full.csv"},
    "bamboopalms":    {"label": "Bamboos & Palms",     "category_url": "/product-category/artificial-bamboo-and-palms/",           "output": HERE / "dp_bamboopalms_full.csv"},
    "planters":       {"label": "Planters",            "category_url": "/product-category/planters/",                             "output": HERE / "dp_planters_full.csv"},
}
```

- [ ] **Step 2: Verify the argparse choices list still works**

The `--catalog` argument uses `list(CATALOGS.keys())` dynamically, so no change is needed there. Confirm by searching for `choices=` in `scrape_full.py` — it should read:

```python
choices=["all"] + list(CATALOGS.keys()),
```

If it lists keys explicitly (not dynamically), update it to match the pattern above.

- [ ] **Step 3: Smoke-test the new keys are recognised**

Run in the project directory:

```
python scrape_full.py --help
```

Expected output includes all 12 catalog keys in the `--catalog` choices list:
```
choices: all, outdoor, verticalgardens, topiary, trees, outdoortrees, hedges, hangingplants, shrubs, ivy, floweringplants, bamboopalms, planters
```

---

## Task 2: Expand CATALOGS in verify.py

**Files:**
- Modify: `verify.py` lines 42–45

- [ ] **Step 1: Open verify.py and replace the CATALOGS dict**

Find this block (lines 42–45):

```python
CATALOGS = {
    "outdoor":         "/product-category/artificial-outdoor-plants/",
    "verticalgardens": "/product-category/vertical-garden-green-walls/",
}
```

Replace with:

```python
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
```

- [ ] **Step 2: Check that load_csv() derives the filename from the key correctly**

`load_csv()` constructs: `HERE / f"dp_{catalog_key}_full.csv"`. This works for all 12 keys — confirm visually that the pattern matches each output filename in the CATALOGS dict above (e.g. key `hangingplants` → `dp_hangingplants_full.csv`).

---

## Task 3: Update run.bat catalog loop

**Files:**
- Modify: `run.bat` line 15

- [ ] **Step 1: Update the for loop in run.bat**

Find this line (line 15):

```bat
for %%C in (outdoor verticalgardens) do (
```

Replace with:

```bat
for %%C in (outdoor verticalgardens topiary trees outdoortrees hedges hangingplants shrubs ivy floweringplants bamboopalms planters) do (
```

No other changes to `run.bat` are needed — the rest of the loop body is already generic.

---

## Task 4: Commit the catalog expansion

**Files:** All three modified files.

- [ ] **Step 1: Commit**

```bash
git add scrape_full.py verify.py run.bat docs/superpowers/plans/2026-05-18-dp-expand-catalogs.md
git commit -m "feat: expand DP scraper from 2 to 12 catalogs

Adds topiary, trees, outdoortrees, hedges, hangingplants, shrubs, ivy,
floweringplants, bamboopalms, planters. Fixes 524 false-positive
discontinuation flags in FLORA SKU pipeline caused by missing scrape coverage."
```

---

## Task 5: Test-scrape one new catalog

Validate that a newly added catalog works end-to-end before running all 12.

- [ ] **Step 1: Refresh session**

```
python save_session.py
```

Expected: `Session saved to auth.json` (or equivalent success message).

- [ ] **Step 2: Run --test mode on one new catalog**

```
python scrape_full.py --catalog topiary --test
```

`--test` scrapes only the first page load (~10-20 products), so this completes in ~60 seconds.

Expected output:
```
# CATALOG : Topiary
...
Phase 1 done in X.Xs  —  N products
Phase 2 done in X.Xs
=======================================================
  N products written to dp_topiary_full.csv
```

No errors, `scrape_status` column shows `ok` for scraped rows.

- [ ] **Step 3: Spot-check the output CSV**

Open `dp_topiary_full.csv` and confirm:
- `sku` column contains numeric strings (e.g. `1009697`)
- `name` column contains product names
- `wholesale_price` is populated (requires auth — empty means session failed)
- `in_stock` is `In Stock` or `Out of Stock`

If `wholesale_price` is empty for all rows, the session has expired — re-run `python save_session.py` (or `login.bat`) and retry.

---

## Task 6: Copy new CSVs to FLORA SKU pipeline input

After a full scrape, copy the new catalog CSVs into the SKU pipeline's input directory.

- [ ] **Step 1: After full run.bat completes, copy all new CSVs**

New catalogs produce these files in the `FLORA DP Site Scrape` directory:
```
dp_topiary_full.csv
dp_trees_full.csv
dp_outdoortrees_full.csv
dp_hedges_full.csv
dp_hangingplants_full.csv
dp_shrubs_full.csv
dp_ivy_full.csv
dp_floweringplants_full.csv
dp_bamboopalms_full.csv
dp_planters_full.csv
```

Copy them to:
```
C:\Users\admin\Desktop\Claude\Development\FLORA SKU System Max V1\input\suppliers\DP\
```

The existing `dp_outdoor_full.csv` and `dp_verticalgardens_full.csv` are already there — copy only the new ones (or overwrite all for a clean refresh).

- [ ] **Step 2: Re-run the FLORA SKU pipeline and check the discontinue count**

In `FLORA SKU System Max V1`:
```
run.bat
```

Then check:
```
grep -c "DP" output/actions/action_discontinue.csv
```

Before this fix: 524 DP products flagged. After: should be dramatically lower (only genuinely discontinued products remain).
