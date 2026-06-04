"""
login.py — Designer Plants auth session saver
Logs in headlessly and saves storage_state to auth.json.

Credentials (in priority order):
  1. Environment variables:  DP_EMAIL  and  DP_PASSWORD
  2. credentials.json in this directory:  {"email": "...", "password": "..."}
  3. Interactive prompt (fallback — skipped when --force is used)

Usage:
    python login.py            # interactive: prompts before overwriting
    python login.py --force    # non-interactive: always overwrites (used by run.bat)
"""

import argparse
import json
import os
import pathlib
import sys
from playwright.sync_api import sync_playwright

HERE       = pathlib.Path(__file__).parent
AUTH_FILE  = HERE / "auth.json"
CREDS_FILE = HERE / "credentials.json"
LOGIN_URL  = "https://designerplants.com.au/my-account/"
CHECK_URL  = "https://designerplants.com.au/product-category/artificial-outdoor-plants/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def load_credentials(force: bool) -> tuple[str, str]:
    email    = os.environ.get("DP_EMAIL")
    password = os.environ.get("DP_PASSWORD")
    if email and password:
        return email, password

    if CREDS_FILE.exists():
        data = json.loads(CREDS_FILE.read_text())
        return data["email"], data["password"]

    if force:
        print("ERROR: No credentials found. Set DP_EMAIL/DP_PASSWORD or create credentials.json.")
        sys.exit(1)

    print("No credentials found in env vars or credentials.json.")
    email    = input("Email / username: ").strip()
    password = input("Password: ").strip()
    return email, password


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Designer Plants login session")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing auth.json without prompting (for automation)")
    args = parser.parse_args()

    print("=" * 60)
    print("  Designer Plants — Save Login Session")
    print("=" * 60)

    if AUTH_FILE.exists() and not args.force:
        overwrite = input(
            f"\nauth.json already exists ({AUTH_FILE}).\n"
            "Overwrite with a new session? [y/N] "
        ).strip().lower()
        if overwrite != "y":
            print("Aborted — existing auth.json kept.")
            sys.exit(0)

    email, password = load_credentials(args.force)
    print(f"\nLogging in as: {email}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=USER_AGENT,
        )
        page = context.new_page()

        print(f"Navigating → {LOGIN_URL}")
        page.goto(LOGIN_URL, wait_until="networkidle")

        print("Filling credentials...")
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', password)

        print("Submitting login form...")
        page.click('button[name="login"]')
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        print(f"Post-submit URL: {page.url}")
        print(f"Verifying session against: {CHECK_URL}")
        page.goto(CHECK_URL, wait_until="networkidle")

        if "my-account" in page.url or "login" in page.url:
            print("\nERROR: Login failed — check your credentials.")
            browser.close()
            sys.exit(1)

        print(f"Session valid — on: {page.url}")
        context.storage_state(path=str(AUTH_FILE))
        browser.close()

    print(f"\nSession saved to {AUTH_FILE}")
    print("  You can now run: python scrape_full.py")


if __name__ == "__main__":
    main()
