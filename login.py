print("=== SCRIPT STARTED ===")

import os
import random
import sys
import time

from seleniumbase import SB

# ================= CONFIG =================
USERNAME = os.getenv("NU_USER")
PASSWORD = os.getenv("NU_PASS")

print("Loaded ENV:")
print("USERNAME:", USERNAME)
print("PASSWORD SET:", bool(PASSWORD))

if not USERNAME or not PASSWORD:
    print("❌ ERROR: NU_USER or NU_PASS not set")
    sys.exit(1)


# ================= HELPERS =================
def human_sleep(a=0.6, b=1.4):
    time.sleep(random.uniform(a, b))


def human_type(sb, selector, text):
    sb.click(selector)
    sb.clear(selector)
    for ch in text:
        sb.send_keys(selector, ch)
        time.sleep(random.uniform(0.05, 0.12))


# ================= LOGIN =================
def login(sb):
    print("Opening NovelUpdates login page...")
    sb.open("https://www.novelupdates.com/login/")

    print("Waiting for Cloudflare...")
    sb.sleep(6)

    print("Trying captcha click (if present)...")
    try:
        if hasattr(sb, "uc_gui_click_captcha"):
            sb.uc_gui_click_captcha()
    except:
        pass  # Captcha handling may not be available
    sb.sleep(4)

    print("Typing username...")
    human_type(sb, "#user_login", USERNAME)
    human_sleep()

    print("Typing password...")
    human_type(sb, "#user_pass", PASSWORD)
    human_sleep()

    print("Clicking login...")
    sb.click('input[name="wp-submit"]')
    sb.sleep(8)

    # Robust login confirmation
    if sb.is_text_visible(USERNAME):
        print("✅ LOGIN CONFIRMED")
        return True

    if sb.is_element_present('a[href*="logout"]'):
        print("✅ LOGIN CONFIRMED")
        return True

    sb.open("https://www.novelupdates.com/user/")
    sb.sleep(3)

    if sb.is_text_visible("Profile"):
        print("✅ LOGIN CONFIRMED")
        return True

    print("❌ LOGIN CHECK FAILED (session may still exist)")
    return False


# ================= ADD RELEASE =================
def open_add_release(sb):
    print("Opening Add Release page...")
    sb.open("https://www.novelupdates.com/add-release/")
    sb.sleep(5)

    if sb.is_text_visible("Add Release"):
        print("✅ Add Release page loaded")
        return True

    print("❌ Failed to load Add Release page")
    return False


def fill_add_release(
    sb, series_name, release_name, release_link, group_name, release_date=None
):
    print("Filling Add Release form (plain typing only)...")

    print("→ Series")
    human_type(sb, "#title_change_100", series_name)

    print("→ Release")
    human_type(sb, "#arrelease", release_name)

    print("→ Link")
    human_type(sb, "#arlink", release_link)

    print("→ Group")
    human_type(sb, "#group_change_100", group_name)

    if release_date:
        print("→ Release Date")
        human_type(sb, "#ardate", release_date)

    print("✅ Form filled (NOT submitted)")


# ================= MAIN =================
def main():
    print("=== ENTERED MAIN ===")

    with SB(uc=True, headless=False) as sb:
        print("Browser launched")

        if not login(sb):
            sb.sleep(10)
            return

        if not open_add_release(sb):
            sb.sleep(10)
            return

        fill_add_release(
            sb,
            series_name="Solo Leveling",
            release_name="v2c10",
            release_link="https://example.com/chapter-10",
            group_name="MyTranslationGroup",
            release_date=None,
        )

        print("🟡 NOT submitting. Browser will stay open.")
        sb.sleep(30)


# ================= ENTRY =================
if __name__ == "__main__":
    main()
