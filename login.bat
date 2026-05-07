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
