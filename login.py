"""
login.py — One-time Designer Plants auth session saver
Run this once to log in and save your session. After that, scrape_full.py
uses the saved session automatically — no further logins needed.

Usage:
    python login.py
"""

import pathlib
import sys
from playwright.sync_api import sync_playwright

HERE      = pathlib.Path(__file__).parent
AUTH_FILE = HERE / "auth.json"
LOGIN_URL = "https://designerplants.com.au/my-account/"
CHECK_URL = "https://designerplants.com.au/product-category/artificial-outdoor-plants/"


def main():
    print("=" * 60)
    print("  Designer Plants — One-time login")
    print("=" * 60)

    if AUTH_FILE.exists():
        overwrite = input(
            f"\nauth.json already exists ({AUTH_FILE}).\n"
            "Overwrite with a new session? [y/N] "
        ).strip().lower()
        if overwrite != "y":
            print("Aborted — existing auth.json kept.")
            sys.exit(0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = context.new_page()

        print(f"\nOpening browser → {LOGIN_URL}")
        page.goto(LOGIN_URL)

        print("\nPlease log in to your Designer Plants account in the browser window.")
        print("When you are fully logged in and can browse products,")
        print("press Enter here to save the session ...")
        input()

        # Verify we are actually logged in
        page.goto(CHECK_URL)
        page.wait_for_load_state("domcontentloaded")
        if "my-account" in page.url or "login" in page.url:
            print("\nWarning: looks like you may not be logged in yet.")
            print("Please try again and make sure you can see products.")
            browser.close()
            sys.exit(1)

        context.storage_state(path=str(AUTH_FILE))
        browser.close()

    print(f"\nSession saved to {AUTH_FILE}")
    print("  You can now run: python scrape_full.py")


if __name__ == "__main__":
    main()
