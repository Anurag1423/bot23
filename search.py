import os
import random
import re
import sys
import time

from seleniumbase import SB

# Import NU crawler functions
from nu_crawler import crawl_nu_chapters, human_type, login, parse_vol_ch


# ================= HELPERS =================
def human_sleep(a=0.6, b=1.4):
    time.sleep(random.uniform(a, b))


# ================= CONFIG =================
USERNAME = os.getenv("NU_USER")
PASSWORD = os.getenv("NU_PASS")

FENRI_URL = (
    "https://fenrirealm.com/series/how-could-the-villainous-young-master-be-a-saintess"
)
NU_URL = "https://www.novelupdates.com/series/how-could-the-villainous-young-master-be-a-saintess/?pg=1&grp=78568"
GROUP_NAME = "Fenrir Realm"  # Translation group name for submissions

if not USERNAME or not PASSWORD:
    print("❌ ERROR: NU_USER or NU_PASS not set")
    sys.exit(1)


# ================= FENRIR =================
def crawl_fenrir_chapters(sb):
    print("[*] Crawling Fenrir chapters...")
    sb.open(FENRI_URL)
    sb.wait_for_element("#list-chapter", timeout=15)

    # Only look for chapters in the "Free Chapters" tab panel
    # Free chapters are in: [role="tabpanel"][data-value="free"]
    free_tab_selector = '[role="tabpanel"][data-value="free"]'

    # Scroll to load all chapters in the free tab
    last = 0
    for _ in range(20):
        sb.execute_script("window.scrollBy(0, 6000);")
        sb.sleep(1.2)
        # Count only free chapter links
        cur = len(sb.find_elements(f"{free_tab_selector} a.btn-chapter"))
        if cur == last and cur > 0:
            break
        last = cur

    chapters = set()
    premium_count = 0

    # Get only chapters from the free tab panel
    for a in sb.find_elements(f"{free_tab_selector} a.btn-chapter"):
        # Double check: free chapters should link to /series/, not /auth/login
        href = (a.get_attribute("href") or "").lower()

        # Skip any that link to auth/login (shouldn't happen in free tab, but safety check)
        if "auth" in href or "login" in href:
            premium_count += 1
            continue

        title = a.text or a.get_attribute("title")
        parsed = parse_vol_ch(title)
        if parsed:
            chapters.add(parsed)

    print(
        f"✅ Fenrir chapters found: {len(chapters)} (skipped {premium_count} premium chapters)"
    )
    return chapters


# ================= ADD RELEASE =================
def open_add_release(sb):
    """Open the Add Release page on NovelUpdates."""
    print("[*] Opening Add Release page...")
    sb.open("https://www.novelupdates.com/add-release/")
    sb.sleep(5)

    if sb.is_text_visible("Add Release"):
        print("✅ Add Release page loaded")
        return True

    print("❌ Failed to load Add Release page")
    return False


def format_chapter_name(vol, ch):
    """Format chapter as 'v2c77' or 'c16'."""
    if vol is not None:
        return f"v{vol}c{ch}"
    else:
        return f"c{ch}"


def build_fenrir_chapter_url(chapter_num, fenrir_base_url):
    """Build Fenrir chapter URL from base URL and chapter number."""
    # Extract series slug from base URL
    # e.g., "https://fenrirealm.com/series/series-name" -> "series-name"
    series_slug = fenrir_base_url.split("/series/")[-1].rstrip("/")

    # Fenrir chapter URLs are typically: /series/series-name/chapter-number
    return f"https://fenrirealm.com/series/{series_slug}/{chapter_num}"


def fill_add_release(
    sb, series_name, release_name, release_link, group_name, release_date=None
):
    """Fill the Add Release form (does NOT submit)."""
    print(f"[*] Filling form for: {release_name}")

    print("  → Series")
    human_type(sb, "#title_change_100", series_name)

    print("  → Release")
    human_type(sb, "#arrelease", release_name)

    print("  → Link")
    human_type(sb, "#arlink", release_link)

    print("  → Group")
    human_type(sb, "#group_change_100", group_name)

    if release_date:
        print("  → Release Date")
        human_type(sb, "#ardate", release_date)

    print("  ✅ Form filled (NOT submitted)")


def prepare_submissions(sb, missing_chapters, series_name, fenrir_base_url, group_name):
    """Prepare submissions for missing chapters (fills forms but doesn't submit)."""
    if not missing_chapters:
        print("[*] No missing chapters to submit")
        return

    print(f"\n[*] Preparing to submit {len(missing_chapters)} missing chapters...")

    if not open_add_release(sb):
        print("❌ Could not open Add Release page")
        return

    print("\n🟡 SUBMISSIONS PREPARED BUT NOT SUBMITTED")
    print("=" * 60)

    for idx, (vol, ch) in enumerate(missing_chapters, 1):
        release_name = format_chapter_name(vol, ch)
        release_link = build_fenrir_chapter_url(ch, fenrir_base_url)

        print(f"\n[{idx}/{len(missing_chapters)}] Chapter: {release_name}")
        print(f"  Link: {release_link}")

        # Fill the form
        fill_add_release(
            sb,
            series_name=series_name,
            release_name=release_name,
            release_link=release_link,
            group_name=group_name,
            release_date=None,
        )

        # Don't submit - just wait a bit between chapters
        human_sleep(1, 2)
        print("  ⚠️  NOT SUBMITTED (preview only)")

    print("\n" + "=" * 60)
    print("🟡 All forms filled but NOT submitted")
    print("   To enable submission, uncomment the submit button click in the code")


# ================= MAIN =================
def main():
    with SB(uc=True, headless=True) as sb:
        fenrir = crawl_fenrir_chapters(sb)
        # Login once and let NU crawler use the session
        login(sb, USERNAME, PASSWORD)
        nu = crawl_nu_chapters(
            sb, NU_URL, require_login=False, username=USERNAME, password=PASSWORD
        )

        missing = sorted(fenrir - nu)

        print("\n" + "=" * 60)
        print(f"Missing chapters on NovelUpdates: {len(missing)}")
        print("=" * 60)
        for vol, ch in missing:
            if vol is not None:
                print(f"Vol {vol} Ch {ch}")
            else:
                print(f"Ch {ch}")

        # Prepare submissions (but don't submit)
        if missing:
            # Extract series name from URL (last part of path)
            series_name = NU_URL.split("/series/")[-1].split("/")[0].split("?")[0]
            # Replace hyphens with spaces and title case for display
            series_display_name = series_name.replace("-", " ").title()

            print("\n" + "=" * 60)
            print("Preparing submissions...")
            print("=" * 60)

            # Note: This will fill forms but NOT submit
            # Set headless=False if you want to see the browser
            prepare_submissions(
                sb,
                missing,
                series_name=series_display_name,
                fenrir_base_url=FENRI_URL,
                group_name=GROUP_NAME,
            )


if __name__ == "__main__":

    main()
