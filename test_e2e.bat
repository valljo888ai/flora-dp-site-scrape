@echo off
cd /d "%~dp0"
echo ============================================================
echo  Designer Plants Scraper — End-to-End Smoke Test
echo  (5 products from the 'outdoor' catalog)
echo ============================================================
echo.

echo [1/3] Refreshing session...
python login.py --force
if %ERRORLEVEL% neq 0 (
    echo ERROR: Login failed. See output above.
    pause
    exit /b 1
)
echo.

echo [2/3] Scraping 5 products from outdoor catalog...
python scrape_full.py --catalog outdoor --test --limit 5 --concurrency 2
if %ERRORLEVEL% neq 0 (
    echo ERROR: Scraper exited with an error. See output above.
    pause
    exit /b 1
)
echo.

echo [3/3] Verifying output CSV...
python verify.py --catalogs outdoor
if %ERRORLEVEL% neq 0 (
    echo.
    echo SMOKE TEST FAILED — see verification output above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  SMOKE TEST PASSED
echo ============================================================
pause
