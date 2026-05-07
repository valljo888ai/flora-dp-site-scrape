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
