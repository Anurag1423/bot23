"""
NovelUpdates (NU) Chapter Crawler

This module can be used independently or imported by other scripts.
When run standalone, it crawls chapters from a NovelUpdates series URL.
"""

import argparse
import os
import random
import re
import sys
import time

from seleniumbase import SB

# ================= CONFIG =================
USERNAME = os.getenv("NU_USER")
PASSWORD = os.getenv("NU_PASS")

# ================= REGEX =================
CHAPTER_RE = re.compile(
    r"""
    (?:
        vol(?:ume)?\.?\s*(\d+)\s*
    )?
    (?:.*?)?
    (?:ch(?:apter)?|c)\.?\s*(\d+)
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ================= UTILITIES =================
def parse_vol_ch(text):
    """Parse volume and chapter number from text."""
    if not text:
        return None

    # Handle "v1c105" format first (volume + chapter, no spaces)
    # This must be checked before simple "c" format to avoid matching just "c105"
    vol_ch_compact = re.search(r"\bv(\d+)c(\d+)\b", text, re.IGNORECASE)
    if vol_ch_compact:
        vol = int(vol_ch_compact.group(1))
        ch = int(vol_ch_compact.group(2))
        return (vol, ch)

    # Handle "v2 c77" or "vol 2 c77" format (with spaces)
    vol_ch_spaced = re.search(
        r"\b(?:vol(?:ume)?|v)\.?\s*(\d+)\s+c\.?\s*(\d+)\b", text, re.IGNORECASE
    )
    if vol_ch_spaced:
        vol = int(vol_ch_spaced.group(1))
        ch = int(vol_ch_spaced.group(2))
        return (vol, ch)

    # Handle simple "c5", "c4" format (chapter only, no volume)
    simple_c_match = re.search(r"\bc\.?\s*(\d+)\b", text, re.IGNORECASE)
    if simple_c_match:
        ch = int(simple_c_match.group(1))
        return (None, ch)

    # Try the full regex pattern for other formats
    m = CHAPTER_RE.search(text)
    if not m:
        return None
    vol = int(m.group(1)) if m.group(1) else None
    ch = int(m.group(2))
    return (vol, ch)


def human_type(sb, selector, text):
    """Type text character by character to mimic human behavior."""
    sb.click(selector)
    sb.clear(selector)
    for ch in text:
        sb.send_keys(selector, ch)
        time.sleep(random.uniform(0.05, 0.12))


# ================= LOGIN =================
def login(sb, username=None, password=None):
    """
    Log into NovelUpdates.

    Args:
        sb: SeleniumBase instance
        username: Optional username (defaults to NU_USER env var)
        password: Optional password (defaults to NU_PASS env var)

    Returns:
        bool: True if login successful, False otherwise
    """
    username = username or USERNAME
    password = password or PASSWORD

    if not username or not password:
        print("❌ ERROR: Username and password required for login")
        return False

    print("[*] Logging into NovelUpdates...")
    sb.open("https://www.novelupdates.com/login/")
    sb.sleep(6)
    # Try to handle captcha if present (if method exists)
    try:
        if hasattr(sb, "uc_gui_click_captcha"):
            sb.uc_gui_click_captcha()
    except:
        pass  # Captcha handling may not be available
    sb.sleep(4)

    human_type(sb, "#user_login", username)
    human_type(sb, "#user_pass", password)
    sb.click('input[name="wp-submit"]')
    sb.sleep(8)

    print("✅ LOGIN CONFIRMED")
    return True


# ================= NU CRAWLER =================
def crawl_nu_chapters(
    sb, nu_url, require_login=True, username=None, password=None, debug=False
):
    """
    Crawl chapters from a NovelUpdates series page.

    Args:
        sb: SeleniumBase instance
        nu_url: URL of the NovelUpdates series page
        require_login: Whether to log in before crawling (default: True)
        username: Optional username for login
        password: Optional password for login
        debug: If True, print debug information

    Returns:
        set: Set of tuples (vol, ch) where vol can be None
    """
    if require_login:
        if not login(sb, username, password):
            print("❌ Login failed, cannot crawl chapters")
            return set()

    print("[*] Crawling NovelUpdates chapters...")
    sb.open(nu_url)
    sb.sleep(3)

    # Try to open the reading popup
    try:
        sb.wait_for_element("span.my_popupreading_open", timeout=10)
        sb.click("span.my_popupreading_open")
        sb.sleep(2)
        print("[*] Opened reading popup")
    except Exception as e:
        print(f"❌ Failed to open reading popup: {e}")
        print("[*] Trying alternative selector...")
        # Try alternative selectors
        alt_selectors = [
            "a.my_popupreading_open",
            ".my_popupreading_open",
            "[class*='popupreading']",
        ]
        opened = False
        for alt_sel in alt_selectors:
            try:
                if sb.is_element_present(alt_sel):
                    sb.click(alt_sel)
                    sb.sleep(2)
                    opened = True
                    print(f"[*] Opened popup using selector: {alt_sel}")
                    break
            except:
                continue
        if not opened:
            print("❌ Could not open reading popup")
            return set()

    chapters = set()
    page_num = 1

    while True:
        # Try primary selector first
        selector = "#my_popupreading ol.sp_chp li span"
        elements = []

        try:
            sb.wait_for_element(selector, timeout=10)
            elements = sb.find_elements(selector)
        except:
            # Try alternative selectors for span
            alt_selectors_span = [
                "#my_popupreading ol li span",
                "#my_popupreading .sp_chp li span",
                ".sp_chp li span",
                "#my_popupreading li span",
            ]
            for alt_sel in alt_selectors_span:
                if sb.is_element_present(alt_sel):
                    selector = alt_sel
                    elements = sb.find_elements(alt_sel)
                    print(f"[*] Using alternative span selector: {alt_sel}")
                    break

            # If no spans found, try anchor tags
            if not elements:
                alt_selectors_a = [
                    "#my_popupreading ol.sp_chp li a",
                    "#my_popupreading ol li a",
                    "#my_popupreading .sp_chp li a",
                    ".sp_chp li a",
                ]
                for alt_sel in alt_selectors_a:
                    if sb.is_element_present(alt_sel):
                        selector = alt_sel
                        elements = sb.find_elements(alt_sel)
                        print(f"[*] Using anchor tag selector: {alt_sel}")
                        break

            if not elements:
                print("❌ Could not find chapter elements")
                if debug:
                    # Debug: print page source snippet
                    try:
                        popup_html = sb.get_attribute("#my_popupreading", "innerHTML")[
                            :500
                        ]
                        print(f"[DEBUG] Popup HTML snippet: {popup_html}")
                    except:
                        pass
                break

        print(f"[*] Page {page_num}: Found {len(elements)} elements using '{selector}'")

        found_on_page = 0
        for s in elements:
            # Try multiple ways to get the chapter title
            title = (
                s.get_attribute("title")
                or s.get_attribute("data-title")
                or s.text
                or ""
            ).strip()

            # If still no title, try getting text from parent or child
            if not title:
                try:
                    # Try parent element
                    parent = s.find_element("xpath", "..")
                    title = parent.get_attribute("title") or parent.text or ""
                except:
                    pass

            if not title:
                continue

            parsed = parse_vol_ch(title)
            if parsed:
                chapters.add(parsed)
                found_on_page += 1
                if debug:
                    print(f"  ✓ Parsed: '{title[:60]}' -> {parsed}")
            else:
                # Debug: print unparseable titles
                if debug or (len(chapters) == 0 and found_on_page < 5):
                    print(f"  [DEBUG] Could not parse: '{title[:80]}'")

        print(
            f"[*] Page {page_num}: Found {found_on_page} parseable chapters (total: {len(chapters)})"
        )

        next_btn = "#my_popupreading a.next.page-numbers"
        if sb.is_element_present(next_btn):
            page_num += 1
            sb.click(next_btn)
            sb.sleep(1.5)
        else:
            break

    print(f"✅ NU chapters found: {len(chapters)}")
    return chapters


# ================= STANDALONE MAIN =================
def main():
    """Standalone entry point for running the NU crawler independently."""
    parser = argparse.ArgumentParser(
        description="Crawl chapters from a NovelUpdates series page"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://www.novelupdates.com/series/kill-the-emperor/",
        help="NovelUpdates series URL (default: kill-the-emperor)",
    )
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="Skip login (may not work for all series)",
    )
    parser.add_argument(
        "--username", help="NovelUpdates username (overrides NU_USER env var)"
    )
    parser.add_argument(
        "--password", help="NovelUpdates password (overrides NU_PASS env var)"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    # Validate credentials if login is required
    username = args.username or USERNAME
    password = args.password or PASSWORD
    if not args.no_login and (not username or not password):
        print("❌ ERROR: NU_USER or NU_PASS not set (or provide --username/--password)")
        print("   Use --no-login to skip authentication (may not work)")
        sys.exit(1)

    # Run crawler
    with SB(uc=True, headless=args.headless) as sb:
        chapters = crawl_nu_chapters(
            sb,
            args.url,
            require_login=not args.no_login,
            username=username,
            password=password,
            debug=args.debug,
        )

        # Print results
        print("\n" + "=" * 60)
        print(f"Found {len(chapters)} chapters")
        print("=" * 60)

        sorted_chapters = sorted(chapters)
        for vol, ch in sorted_chapters:
            if vol is not None:
                print(f"Vol {vol} Ch {ch}")
            else:
                print(f"Ch {ch}")


if __name__ == "__main__":
    main()
