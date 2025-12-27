from datetime import datetime, timezone
import atexit
import json
import logging
import os
from queue import Queue
import random
import re
import signal
import threading
import time
import uuid
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from seleniumbase import SB

# ------------------ SETUP ------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///novels.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

submission_queue = Queue()

_LAST_LIVESEARCH_TS = 0.0


def _throttle_livesearch(min_interval_seconds=2.0):
    global _LAST_LIVESEARCH_TS
    now = time.time()
    wait_s = (_LAST_LIVESEARCH_TS + min_interval_seconds) - now
    if wait_s > 0:
        time.sleep(wait_s)
    _LAST_LIVESEARCH_TS = time.time()


TASKS = {}

# ------------------ DATABASE ------------------


class Novel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    fenrir_url = db.Column(db.String(500), nullable=False)
    nu_url = db.Column(db.String(500), nullable=False)
    group_name = db.Column(db.String(100), default="Fenrir Realm")
    nu_series_id = db.Column(db.String(32))
    nu_group_id = db.Column(db.String(32))
    fenrir_chapters = db.Column(db.Text)
    nu_chapters = db.Column(db.Text)
    last_checked = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "fenrir_url": self.fenrir_url,
            "nu_url": self.nu_url,
            "group_name": self.group_name,
            "nu_series_id": self.nu_series_id,
            "nu_group_id": self.nu_group_id,
            "last_checked": (
                self.last_checked.isoformat() if self.last_checked else None
            ),
        }


with app.app_context():
    db.create_all()

    # Lightweight sqlite migration for new columns.
    try:
        cols = [r[1] for r in db.session.execute(db.text("PRAGMA table_info(novel)")).fetchall()]
        if "nu_series_id" not in cols:
            db.session.execute(db.text("ALTER TABLE novel ADD COLUMN nu_series_id VARCHAR(32)"))
        if "nu_group_id" not in cols:
            db.session.execute(db.text("ALTER TABLE novel ADD COLUMN nu_group_id VARCHAR(32)"))
        db.session.commit()
    except Exception:
        db.session.rollback()

# ------------------ BROWSER MANAGER ------------------


class BrowserManager:
    def __init__(self):
        self.sb = None
        self.ctx = None
        self.lock = threading.Lock()

    def get_sb(self):
        with self.lock:
            if self.sb:
                try:
                    _ = self.sb.driver.window_handles
                except Exception:
                    self.close()

            if not self.sb:
                logger.info("🌐 Launching browser")
                self.ctx = SB(
                    uc=True,
                    headless=False,
                    ad_block_on=False,
                    page_load_strategy="normal",
                )
                self.sb = self.ctx.__enter__()

                self.sb.execute_cdp_cmd(
                    "Network.setBlockedURLs",
                    {
                        "urls": [
                            "*.png",
                            "*.jpg",
                            "*.gif",
                            "*.jpeg",
                            "*.webp",
                            "*.mp4",
                            "*.svg",
                        ]
                    },
                )

                self._login()

            return self.sb

    def _login(self):
        user = os.getenv("NU_USER")
        pw = os.getenv("NU_PASS")
        if not user or not pw:
            logger.warning("⚠️ NU credentials missing, skipping login")
            return

        logger.info("🔑 Logging into NovelUpdates")
        self.sb.open("https://www.novelupdates.com/login/")
        self.sb.wait_for_ready_state_complete(timeout=15)

        try:
            self.sb.wait_for_element_visible("#user_login", timeout=10)
        except Exception:
            logger.error("❌ Login form not found (Cloudflare or layout change)")
            return

        self.sb.type("#user_login", user)
        self.sb.type("#user_pass", pw)
        self.sb.click("#wp-submit")

        self.sb.wait_for_ready_state_complete(timeout=10)
        logger.info("✅ Login attempt finished")

    def close(self):
        with self.lock:
            if not self.ctx:
                self.sb = None
                return

            try:
                self.ctx.__exit__(None, None, None)
            except Exception as e:
                logger.warning("⚠️ Error while closing browser: %s", e)
            finally:
                self.ctx = None
                self.sb = None


browser = BrowserManager()


def _shutdown(*_args):
    try:
        browser.close()
    except Exception as e:
        logger.warning("⚠️ Shutdown cleanup error: %s", e)


atexit.register(_shutdown)

try:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
except Exception:
    pass

# ------------------ HELPERS ------------------


def parse_vol_ch(text):
    if not text:
        return None

    t = (
        str(text)
        .lower()
        .replace("volume", "v")
        .replace("vol.", "v")
        .replace("vol", "v")
        .replace("chapter", "c")
        .replace("ch.", "c")
        .replace("ch", "c")
    )

    # Common patterns:
    # - v3c91
    # - v3 c91
    # - v 3 c 91
    # - c91
    m = re.search(r"\bv\s*(\d+)\s*c\s*(\d+)\b", t, re.IGNORECASE)
    if m:
        try:
            return (int(m.group(1)), int(m.group(2)))
        except Exception:
            return None

    m = re.search(r"\bc\s*(\d+)\b", t, re.IGNORECASE)
    if m:
        try:
            return (0, int(m.group(1)))
        except Exception:
            return None

    return None


def crawl_fenrir_chapters(sb, url):
    sb.open(url)
    try:
        sb.execute_script(
            """
            try {
              localStorage.setItem('discord_modal_disabled', 'true');
              // Some builds may store as a booleanish JSON value.
              localStorage.setItem('discord_modal_disabled_v2', JSON.stringify(true));
            } catch (e) {}
            """
        )
        sb.refresh()
    except Exception:
        pass
    time.sleep(2)

    def _parse_from_href(href):
        if not href:
            return None
        # Common patterns: /<num> or /chapter-<num> or ?chapter=<num>
        m = re.search(r"(?:chapter[-_/]|/)(\d{1,5})(?:/|$)", href, re.IGNORECASE)
        if not m:
            m = re.search(r"[?&]chapter=(\d{1,5})\b", href, re.IGNORECASE)
        if m:
            try:
                return (0, int(m.group(1)))
            except Exception:
                return None
        return None

    chapters = set()
    selectors = [
        'div[role="tabpanel"][data-value="free"] a.btn-chapter',
        'div.grid-chapter a.btn-chapter',
        'a.btn-chapter',
    ]

    try:
        sb.wait_for_element("a.btn-chapter", timeout=15)
    except Exception:
        pass

    try:
        # Best-effort: remove common modal/backdrop overlays if they exist.
        sb.execute_script(
            """
            const selectors = [
              '[role="dialog"]',
              '.modal',
              '.modal-backdrop',
              '.backdrop',
              '.overlay',
            ];
            for (const sel of selectors) {
              document.querySelectorAll(sel).forEach(el => {
                if (el && el.parentNode) el.parentNode.removeChild(el);
              });
            }
            document.body.style.overflow = 'auto';
            """
        )
    except Exception:
        pass

    try:
        # Fenrir uses a scrollable chapter grid; scroll the container, not the window.
        for _ in range(10):
            sb.execute_script(
                """
                const el = document.querySelector('div.grid-chapter');
                if (el) { el.scrollTop = el.scrollHeight; }
                """
            )
            time.sleep(0.35)
    except Exception:
        pass

    for sel in selectors:
        try:
            for a in sb.find_elements(sel):
                href = a.get_attribute("href") or ""
                if "/auth/login" in href:
                    continue
                title = (sb.execute_script("return arguments[0].innerText;", a) or "").strip()
                parsed = parse_vol_ch(title)
                if not parsed:
                    parsed = _parse_from_href(href)
                if parsed:
                    chapters.add(parsed)
        except Exception:
            pass

    # Last resort: parse from page text
    if not chapters:
        try:
            body = sb.get_text("body") or ""
            for m in re.finditer(r"\b(?:v(\d+)\s*)?c(\d+)\b", body, re.IGNORECASE):
                v = int(m.group(1)) if m.group(1) else 0
                c = int(m.group(2))
                chapters.add((v, c))
        except Exception:
            pass

    logger.info("📚 Fenrir chapters: %s", len(chapters))
    return chapters


def crawl_nu_chapters(sb, url, group_id=None):
    final_url = url
    try:
        gid = str(group_id).strip() if group_id is not None else ""
        if gid:
            p = urlparse(url)
            q = parse_qs(p.query)
            q["pg"] = ["1"]
            q["grp"] = [gid]
            final_url = urlunparse(
                (
                    p.scheme,
                    p.netloc,
                    p.path,
                    p.params,
                    urlencode(q, doseq=True),
                    p.fragment,
                )
            )
    except Exception:
        final_url = url

    sb.open(final_url)
    time.sleep(2)

    chapters = set()
    try:
        sb.wait_for_ready_state_complete(timeout=10)
    except Exception:
        pass

    # NU often hides the full chapter list behind a popup. Open it first.
    try:
        sb.execute_script(
            """
            if (typeof list_allchpstwo === 'function') {
              try { list_allchpstwo(); } catch (e) {}
            }
            """
        )
    except Exception:
        pass

    try:
        sb.wait_for_element_visible("#my_popupreading", timeout=8)
        for s in sb.find_elements("#my_popupreading ol.sp_chp span[title]"):
            t = (s.get_attribute("title") or "").strip()
            parsed = parse_vol_ch(t)
            if parsed:
                chapters.add(parsed)
    except Exception:
        # Fallback: attempt clicking the popup open button
        try:
            sb.click(".my_popupreading_open")
            sb.wait_for_element_visible("#my_popupreading", timeout=8)
            for s in sb.find_elements("#my_popupreading ol.sp_chp span[title]"):
                t = (s.get_attribute("title") or "").strip()
                parsed = parse_vol_ch(t)
                if parsed:
                    chapters.add(parsed)
        except Exception:
            pass

    # Prefer releases table when present
    selectors = [
        "table a",
        "a",
    ]

    for sel in selectors:
        try:
            for a in sb.find_elements(sel):
                href = a.get_attribute("href") or ""
                text = (a.text or "").strip()
                parsed = parse_vol_ch(text)
                if not parsed and href:
                    # Sometimes chapter string is in the URL query or slug
                    m = re.search(r"\b(?:v(\d+)\s*)?c(\d+)\b", href, re.IGNORECASE)
                    if m:
                        v = int(m.group(1)) if m.group(1) else 0
                        c = int(m.group(2))
                        parsed = (v, c)
                if parsed:
                    chapters.add(parsed)
        except Exception:
            pass

    # Last resort: parse visible page text
    if not chapters:
        try:
            body = sb.get_text("body") or ""
            for m in re.finditer(r"\b(?:v(\d+)\s*)?c(\d+)\b", body, re.IGNORECASE):
                v = int(m.group(1)) if m.group(1) else 0
                c = int(m.group(2))
                chapters.add((v, c))
        except Exception:
            pass

    logger.info("📚 NU chapters: %s", len(chapters))
    return chapters


def compute_missing(novel):
    f = set(tuple(x) for x in json.loads(novel.fenrir_chapters or "[]"))
    n = set(tuple(x) for x in json.loads(novel.nu_chapters or "[]"))
    return sorted(f - n, key=lambda x: (x[0] or 0, x[1]))


# ------------------ WORKER ------------------


def submission_worker():
    logger.info("🤖 Submission worker started (idle)")

    while True:
        novel, vol, ch = submission_queue.get()
        sb = None

        try:
            sb = browser.get_sb()
            sb.open("https://www.novelupdates.com/add-release/")
            sb.wait_for_element("#arrelease", timeout=15)

            try:
                page_text = sb.get_text("body")
                if "429" in page_text and "Too Many Requests" in page_text:
                    raise Exception("NU rate limited (429)")
            except Exception:
                # If we can't read the body text, proceed; later steps will fail and be handled.
                pass

            def _get_value(selector):
                try:
                    return sb.get_attribute(selector, "value") or ""
                except Exception:
                    return ""

            def _set_value(selector, value):
                try:
                    sb.clear(selector)
                except Exception:
                    pass
                sb.type(selector, value)

            def _type_slow(selector, value, delay_seconds=0.06):
                try:
                    el = sb.driver.find_element("css selector", selector)
                    el.clear()
                    el.click()
                    for ch in value:
                        el.send_keys(ch)
                        time.sleep(delay_seconds)
                except Exception:
                    _set_value(selector, value)

            def _wait_results_then_type(text_selector, container_kind, search_type, full_text):
                # Trigger NU livesearch results, wait until results appear, then finish typing.
                target = (full_text or "").strip()
                if search_type == "series":
                    # Paste-like: send everything except last char fast, then type last char.
                    query = target[:-1] if len(target) > 1 else target
                    last_char = target[-1:] if len(target) > 0 else ""
                elif search_type == "group":
                    query = target[:-1] if len(target) > 1 else target
                    last_char = target[-1:] if len(target) > 0 else ""
                else:
                    if len(target) > 6:
                        query = target[: max(3, len(target) // 2)].rstrip()
                    else:
                        query = target
                    last_char = ""

                if search_type in ("series", "group") and last_char:
                    try:
                        el = sb.driver.find_element("css selector", text_selector)
                        el.clear()
                        el.click()
                        el.send_keys(query)
                    except Exception:
                        _type_slow(text_selector, query + last_char, delay_seconds=0.12)
                else:
                    _type_slow(text_selector, query, delay_seconds=0.12)
                time.sleep(0.35)

                try:
                    sb.execute_script(
                        """
                        const sel = arguments[0];
                        const el = document.querySelector(sel);
                        if (!el) return;
                        el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                        """,
                        text_selector,
                    )
                except Exception:
                    pass

                try:
                    _throttle_livesearch(2.0)
                    sb.execute_script(
                        "if (typeof showResult === 'function') { showResult(arguments[0], '100', arguments[1]); }",
                        query,
                        search_type,
                    )
                except Exception:
                    pass

                # Per workflow: do not wait for dropdown; type final char immediately.
                if search_type in ("series", "group") and last_char:
                    try:
                        el = sb.driver.find_element("css selector", text_selector)
                        el.send_keys(last_char)
                        try:
                            sb.execute_script(
                                """
                                const sel = arguments[0];
                                const el = document.querySelector(sel);
                                if (!el) return;
                                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                                """,
                                text_selector,
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass

                time.sleep(0.2)
                return

            if getattr(novel, "nu_series_id", None):
                sb.execute_script(
                    """
                    const seriesId = arguments[0];
                    const seriesName = arguments[1];
                    const hid = document.querySelector('#title100');
                    const txt = document.querySelector('#title_change_100');
                    if (hid) hid.value = seriesId;
                    if (txt) txt.value = seriesName;
                    """,
                    str(novel.nu_series_id),
                    novel.name,
                )
            else:
                _wait_results_then_type("#title_change_100", "livesearch", "series", novel.name)

            release = f"v{vol}c{ch}" if vol else f"c{ch}"
            link = f"{novel.fenrir_url.rstrip('/')}/{ch}"

            _set_value("#arrelease", release)
            _set_value("#arlink", link)

            if getattr(novel, "nu_group_id", None):
                sb.execute_script(
                    """
                    const groupId = arguments[0];
                    const groupName = arguments[1];
                    const hid = document.querySelector('#group100');
                    const txt = document.querySelector('#group_change_100');
                    if (hid) hid.value = groupId;
                    if (txt) txt.value = groupName;
                    """,
                    str(novel.nu_group_id),
                    novel.group_name,
                )
            else:
                _wait_results_then_type("#group_change_100", "livesearchgroup", "group", novel.group_name)

            title_val = _get_value("#title_change_100").strip()
            group_val = _get_value("#group_change_100").strip()
            arrelease_val = _get_value("#arrelease").strip()
            arlink_val = _get_value("#arlink").strip()
            if not title_val:
                raise Exception("Missing Series")
            if not group_val:
                raise Exception("Missing Group")
            if not arrelease_val:
                raise Exception("Release field empty")
            if not arlink_val:
                raise Exception("Link field empty")

            sb.click("#submit")
            logger.info(f"✅ Submitted {novel.name} {release}")

            time.sleep(random.randint(180, 300))

        except Exception as e:
            if "rate limited (429)" in str(e).lower() or "too many requests" in str(e).lower():
                # Back off and retry later by re-queueing the task.
                try:
                    submission_queue.put((novel, vol, ch))
                except Exception:
                    pass
                sleep_s = random.randint(180, 300)
                logger.warning("⏳ NU rate limited. Backing off %ss", sleep_s)
                time.sleep(sleep_s)
                continue
            if "Active window was already closed" in str(e):
                try:
                    browser.close()
                except Exception:
                    pass
                time.sleep(1)
                continue
            try:
                logger.error(
                    "❌ Submission failed: %s | title=%r group=%r release=%r link=%r",
                    e,
                    _get_value("#title_change_100"),
                    _get_value("#group_change_100"),
                    _get_value("#arrelease"),
                    _get_value("#arlink"),
                )
            except Exception:
                logger.error(f"❌ Submission failed: {e}")
        finally:
            try:
                browser.close()
            except Exception:
                pass


# ------------------ API ------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/novels", methods=["GET", "POST"])
def novels():
    if request.method == "POST":
        data = request.json
        n = Novel(
            name=data["name"],
            fenrir_url=data["fenrir_url"],
            nu_url=data["nu_url"],
            group_name=data.get("group_name", "Fenrir Realm"),
            nu_series_id=(str(data.get("nu_series_id")).strip() if data.get("nu_series_id") else None),
            nu_group_id=(str(data.get("nu_group_id")).strip() if data.get("nu_group_id") else None),
        )
        db.session.add(n)
        db.session.commit()
        return jsonify(n.to_dict()), 201

    return jsonify([n.to_dict() for n in Novel.query.all()])


@app.route("/api/novels/<int:novel_id>/refresh", methods=["POST"])
def refresh(novel_id):
    novel = db.session.get(Novel, novel_id)
    if not novel:
        return jsonify({"error": "Novel not found"}), 404

    task_id = uuid.uuid4().hex
    TASKS[task_id] = {
        "status": "running",
        "progress": 0,
        "message": "Starting...",
    }

    def task():
        try:
            TASKS[task_id]["progress"] = 10
            TASKS[task_id]["message"] = "Loading Fenrir..."
            sb = browser.get_sb()
            f = crawl_fenrir_chapters(sb, novel.fenrir_url)

            TASKS[task_id]["progress"] = 55
            TASKS[task_id]["message"] = "Loading NovelUpdates..."
            n = crawl_nu_chapters(sb, novel.nu_url, group_id=getattr(novel, "nu_group_id", None))

            with app.app_context():
                nobj = db.session.get(Novel, novel_id)
                if not nobj:
                    raise Exception("Novel not found")
                nobj.fenrir_chapters = json.dumps(list(f))
                nobj.nu_chapters = json.dumps(list(n))
                nobj.last_checked = datetime.now(timezone.utc)
                db.session.commit()

            TASKS[task_id]["progress"] = 100
            TASKS[task_id]["message"] = "Done"
            TASKS[task_id]["status"] = "completed"
        except Exception as e:
            TASKS[task_id]["status"] = "error"
            TASKS[task_id]["message"] = str(e)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    threading.Thread(target=task, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/tasks/<task_id>")
def task_status(task_id):
    t = TASKS.get(task_id)
    if not t:
        return jsonify({"status": "error", "message": "Task not found"}), 404
    return jsonify(t)


@app.route("/api/novels/<int:novel_id>/missing")
def missing(novel_id):
    novel = db.session.get(Novel, novel_id)
    if not novel:
        return jsonify({"error": "Novel not found"}), 404
    missing = compute_missing(novel)
    return jsonify(
        {"count": len(missing), "missing": [{"vol": v, "ch": c} for v, c in missing]}
    )


@app.route("/api/novels/<int:novel_id>/submit", methods=["POST"])
def submit(novel_id):
    novel = db.session.get(Novel, novel_id)
    data = request.json

    for c in data["chapters"]:
        submission_queue.put((novel, c.get("vol"), c["ch"]))

    return jsonify({"queued": len(data["chapters"])})


# ------------------ MAIN ------------------

if __name__ == "__main__":
    logger.info("🚀 Starting Flask server")
    threading.Thread(target=submission_worker, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
