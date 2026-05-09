"""
login.py — One-time Designer Plants auth session saver
Automatically fills credentials and saves the session.  After that,
scrape_full.py uses the saved session — no further logins needed.

Credentials (in priority order):
  1. Environment variables:  DP_EMAIL  and  DP_PASSWORD
  2. credentials.json in this directory:  {"email": "...", "password": "..."}
  3. Interactive prompt (fallback)

Usage:
    python login.py
"""

import json
import os
import pathlib
import sys
from playwright.sync_api import sync_playwright

HERE      = pathlib.Path(__file__).parent
AUTH_FILE = HERE / "auth.json"
CREDS_FILE = HERE / "credentials.json"
LOGIN_URL = "https://designerplants.com.au/my-account/"
CHECK_URL = "https://designerplants.com.au/product-category/artificial-outdoor-plants/"


def load_credentials():
    email    = os.environ.get("DP_EMAIL")
    password = os.environ.get("DP_PASSWORD")
    if email and password:
        return email, password

    if CREDS_FILE.exists():
        data = json.loads(CREDS_FILE.read_text())
        return data["email"], data["password"]

    print("No credentials found in env vars or credentials.json.")
    email    = input("Email / username: ").strip()
    password = input("Password: ").strip()
    return email, password


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

    email, password = load_credentials()
    print(f"\nLogging in as: {email}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = context.new_page()

        print(f"Navigating → {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#username", timeout=15_000)

        page.fill("#username", email)
        page.fill("#password", password)
        page.click("button[name=login]")
        page.wait_for_load_state("domcontentloaded")

        # Verify login succeeded
        page.goto(CHECK_URL)
        page.wait_for_load_state("domcontentloaded")
        if "my-account" in page.url or "login" in page.url:
            print("\nERROR: Login failed — check your credentials.")
            browser.close()
            sys.exit(1)

        context.storage_state(path=str(AUTH_FILE))
        browser.close()

    print(f"\nSession saved to {AUTH_FILE}")
    print("  You can now run: python scrape_full.py")


if __name__ == "__main__":
    main()
