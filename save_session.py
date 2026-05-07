"""
One-shot script: log in headlessly and save storage_state to auth.json.
Used by run.bat to refresh the session before each catalog run without
popping up a visible browser window.

Usage:
    python save_session.py
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL   = "https://designerplants.com.au"
AUTH_FILE  = Path(__file__).parent / "auth.json"
USERNAME   = "floradesigns.com.au"
PASSWORD   = "rfvEhnn9kc#O"
LOGIN_URL  = f"{BASE_URL}/my-account/"
CHECK_URL  = f"{BASE_URL}/product-category/artificial-outdoor-plants/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page    = await context.new_page()

        print("Navigating to login page...")
        await page.goto(LOGIN_URL, wait_until="networkidle")

        print("Filling credentials...")
        # WooCommerce standard login form uses name="username" (not email)
        # Submit button is: <button type="submit" name="login" ...>
        await page.fill('input[name="username"]', USERNAME)
        await page.fill('input[name="password"]', PASSWORD)

        print("Submitting login form...")
        await page.click('button[name="login"]')

        # Wait for navigation after submit — WooCommerce typically stays on
        # /my-account/ but renders the dashboard, or redirects elsewhere.
        # Rather than guessing the post-login URL, just wait a few seconds
        # and then navigate directly to the check URL.
        print("Waiting for post-login redirect...")
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass  # timeout is fine — page may already be stable

        print(f"Post-submit URL: {page.url}")

        # Verify access to a category page (requires login on this site)
        print(f"Verifying session against: {CHECK_URL}")
        await page.goto(CHECK_URL, wait_until="networkidle")

        if "my-account" in page.url or "login" in page.url:
            print("ERROR: Redirected to login page — session not valid.")
            print(f"       Current URL: {page.url}")
            print("       Check credentials or selector logic.")
            await browser.close()
            raise SystemExit(1)

        print(f"Session valid — on: {page.url}")

        storage = await context.storage_state()
        AUTH_FILE.write_text(json.dumps(storage, indent=2))
        print(f"auth.json saved to: {AUTH_FILE}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
