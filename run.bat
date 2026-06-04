@echo off
cd /d "%~dp0"
echo ============================================================
echo  Designer Plants Scraper — Full Run
echo ============================================================
echo.

:: If args were passed, treat as single-catalog or option passthrough
if not "%~1"=="" goto single_catalog

:: No args — run all 13 catalogs with a session refresh before each
echo Running all catalogs with session refresh between each.
echo.

for %%C in (outdoor verticalgardens greenwalldiscs topiary trees outdoortrees hedges hangingplants shrubs ivy floweringplants bamboopalms planters) do (
    echo ------------------------------------------------------------
    echo  Refreshing session before catalog: %%C
    echo ------------------------------------------------------------
    python login.py --force
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
python login.py --force
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
python login.py --force
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
