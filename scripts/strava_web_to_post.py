#!/usr/bin/env python3
"""
strava_web_to_post.py — Convert Strava activities into Zola blog posts,
without the Strava API. Instead of OAuth, this uses your logged-in browser
session cookie: copy any XHR request from strava.com as cURL (DevTools →
Network → filter XHR → right-click → Copy as cURL) and the script extracts
the session cookie from your clipboard, then does all requests itself.

The cookie is cached in scripts/.strava_web_config.json (chmod 600) and
revalidated on each run, so you only need to re-copy it when it expires.

Compared to the API version (strava_to_post.py), some stats are unavailable
from the web endpoints: heart rate, cadence, power, calories, gear, device,
location, and max speed. Everything else (name, description, distance,
times, elevation, route, photos) is identical.

Usage:
  python scripts/strava_web_to_post.py                 # interactive picker (recent 20)
  python scripts/strava_web_to_post.py --count 50      # show more activities
  python scripts/strava_web_to_post.py --new           # only not-yet-posted (fetches pages lazily)
  python scripts/strava_web_to_post.py --all           # posts for every activity (skips existing)
  python scripts/strava_web_to_post.py --draft         # mark posts as drafts
  python scripts/strava_web_to_post.py --download-photos
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import strava_to_post as sp

CONFIG_FILE = sp.SCRIPT_DIR / ".strava_web_config.json"
BASE_URL = "https://www.strava.com"
PER_PAGE = 20  # the endpoint hard-caps per_page at 20
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64; rv:149.0) "
              "Gecko/20100101 Firefox/149.0")


# ---------------------------------------------------------------------------
# Clipboard / cookie plumbing
# ---------------------------------------------------------------------------

def read_clipboard() -> str | None:
    for cmd in (
        ["xclip", "-selection", "clipboard", "-o"],
        ["wl-paste", "--no-newline"],
        ["xsel", "--clipboard", "--output"],
    ):
        if shutil.which(cmd[0]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                if result.stdout.strip():
                    return result.stdout
            except subprocess.CalledProcessError:
                continue
    return None


def extract_session_cookie(text: str) -> str | None:
    """Pull the _strava4_session value out of a pasted cURL command, Cookie
    header, or bare cookie value."""
    m = re.search(r"_strava4_session=([A-Za-z0-9]+)", text)
    if m:
        return m.group(1)
    bare = text.strip().strip("'\"")
    if re.fullmatch(r"[a-z0-9]{20,}", bare):
        return bare
    return None


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    CONFIG_FILE.chmod(0o600)


def make_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": f"{BASE_URL}/athlete/training",
    })
    s.cookies.set("_strava4_session", cookie, domain=".strava.com")
    return s


def session_is_valid(session: requests.Session) -> bool:
    try:
        resp = session.get(
            f"{BASE_URL}/athlete/training_activities",
            params={"page": 1, "per_page": 1},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            timeout=30,
        )
        return resp.status_code == 200 and "json" in resp.headers.get("Content-Type", "")
    except requests.RequestException:
        return False


def prompt_for_cookie() -> str:
    print(f"""
Session cookie needed
=====================
1. Open {BASE_URL}/athlete/training in your browser (logged in).
2. Open DevTools (F12) -> Network tab -> filter: XHR.
3. Click to the next page of activities so a 'training_activities' request appears.
4. Right-click the request -> Copy -> Copy as cURL.
""")
    while True:
        input("Press Enter once the cURL command is in your clipboard... ")
        raw = read_clipboard()
        if raw is None:
            print("No clipboard tool found (xclip/wl-paste/xsel) or clipboard empty.")
            print("Paste the cURL command (or just the _strava4_session value), then Ctrl-D:")
            raw = sys.stdin.read()
        cookie = extract_session_cookie(raw or "")
        if cookie:
            return cookie
        print("  Could not find '_strava4_session=...' in that. Try copying again.")


def get_session() -> requests.Session:
    config = load_config()
    cookie = config.get("session_cookie")
    if cookie:
        session = make_session(cookie)
        if session_is_valid(session):
            return session
        print("Saved session cookie has expired.")
    while True:
        cookie = prompt_for_cookie()
        session = make_session(cookie)
        if session_is_valid(session):
            config["session_cookie"] = cookie
            save_config(config)
            print("Session cookie saved.\n")
            return session
        print("  That cookie didn't work (request was rejected). Make sure you're logged in.")


# ---------------------------------------------------------------------------
# Web endpoints
# ---------------------------------------------------------------------------

def fetch_activities_page(session: requests.Session, page: int) -> tuple[list, int]:
    """Return (models, total) for one page of /athlete/training_activities."""
    resp = session.get(
        f"{BASE_URL}/athlete/training_activities",
        params={"page": page, "per_page": PER_PAGE},
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("models", []), data.get("total", 0)


def fetch_streams(session: requests.Session, activity_id: int) -> list:
    """Return the latlng stream as [[lat, lon], ...], or []."""
    try:
        resp = session.get(
            f"{BASE_URL}/activities/{activity_id}/streams",
            params={"stream_types[]": "latlng"},
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json().get("latlng") or []
    except (requests.RequestException, ValueError):
        pass
    return []


def extract_photos_json(html: str) -> list:
    """Extract the `photosJson = [...]` array embedded in an activity page,
    walking brackets so captions containing '];' can't break parsing."""
    key = html.find("photosJson")
    if key == -1:
        return []
    start = html.find("[", key)
    if start == -1:
        return []
    depth, in_str, esc = 0, False, False
    for i in range(start, len(html)):
        c = html[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except json.JSONDecodeError:
                    return []
    return []


def fetch_photos(session: requests.Session, activity_id: int) -> list:
    try:
        resp = session.get(f"{BASE_URL}/activities/{activity_id}", timeout=60)
        if resp.status_code == 200:
            return extract_photos_json(resp.text)
    except requests.RequestException:
        pass
    return []


# ---------------------------------------------------------------------------
# Model normalization: training_activities model -> API-style activity dict
# ---------------------------------------------------------------------------

def normalize_model(model: dict) -> dict:
    """Convert a /athlete/training_activities model into the API-shaped
    activity dict that build_post() and the picker expect."""
    moving = model.get("moving_time_raw") or 0
    distance = model.get("distance_raw") or 0
    raw_local = model.get("start_date_local_raw")
    if raw_local:
        # Epoch shifted so that reading it as UTC yields local wall-clock time.
        start_local = datetime.fromtimestamp(raw_local, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    else:
        start_local = (model.get("start_time") or "")[:19]
    return {
        "id": int(model["id"]),
        "name": model.get("name", "Untitled Activity"),
        "description": model.get("description") or "",
        "sport_type": model.get("sport_type") or model.get("display_type", "Activity"),
        "start_date_local": start_local,
        "distance": distance,
        "moving_time": moving,
        "elapsed_time": model.get("elapsed_time_raw"),
        "total_elevation_gain": model.get("elevation_gain_raw"),
        "average_speed": (distance / moving) if moving else None,
        "has_latlng": bool(model.get("has_latlng")),
        "use_miles": model.get("long_unit") == "miles",
    }


def normalize_photos(photos_raw: list) -> list:
    """Convert photosJson entries into the API-style photo dicts that
    download_banner()/download_photos() expect. Skips videos; the first
    photo is treated as the banner (Strava's highlight ordering)."""
    photos = []
    for p in photos_raw:
        if p.get("video"):
            continue
        url = p.get("large") or p.get("thumbnail")
        if not url:
            continue
        photos.append({"urls": {"5000": url}, "default_photo": not photos})
    return photos


# ---------------------------------------------------------------------------
# Activity listing strategies
# ---------------------------------------------------------------------------

def list_activities(session: requests.Session, count: int) -> list[dict]:
    """Fetch the most recent `count` activities."""
    activities = []
    page = 1
    while len(activities) < count:
        models, total = fetch_activities_page(session, page)
        if not models:
            break
        activities.extend(normalize_model(m) for m in models)
        if len(activities) >= total:
            break
        page += 1
    return activities[:count]


def list_new_activities(session: requests.Session) -> list[dict]:
    """Fetch pages until a whole page contains only already-posted activities
    (activities are reverse-chronological, so older pages are all known too)."""
    known_ids = sp.existing_strava_ids()
    new = []
    page = 1
    fetched = 0
    while True:
        print(f"  Fetching page {page}...")
        models, total = fetch_activities_page(session, page)
        if not models:
            break
        fetched += len(models)
        page_new = [normalize_model(m) for m in models
                    if int(m["id"]) not in known_ids]
        new.extend(page_new)
        print(f"  {len(page_new)} new on this page (total new: {len(new)})")
        if not page_new or fetched >= total:
            break
        page += 1
    return new


def list_all_activities(session: requests.Session) -> list[dict]:
    activities = []
    page = 1
    while True:
        print(f"  Fetching page {page}...")
        models, total = fetch_activities_page(session, page)
        if not models:
            break
        activities.extend(normalize_model(m) for m in models)
        print(f"  Got {len(models)} (total so far: {len(activities)}/{total})")
        if len(activities) >= total:
            break
        page += 1
        time.sleep(0.5)
    return activities


# ---------------------------------------------------------------------------
# Post creation
# ---------------------------------------------------------------------------

def create_post_web(session: requests.Session, activity: dict, draft: bool,
                    dl_photos: bool, skip_existing: bool) -> Path | None:
    use_miles = activity.get("use_miles", False)
    start_local = activity.get("start_date_local", "")
    date_str = start_local[:10] if start_local else datetime.now().strftime("%Y-%m-%d")
    name = activity.get("name", "activity")
    slug = f"{date_str}-{sp.slugify(name)}"
    post_dir = sp.CONTENT_DIR / slug

    if post_dir.exists():
        if skip_existing:
            return None
        ans = input(f"\nDirectory '{post_dir}' already exists. Overwrite? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            sys.exit(0)
    else:
        post_dir.mkdir(parents=True)

    base_url_slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", slug)
    final_url_slug = sp.unique_url_slug(base_url_slug, exclude_dir=post_dir)
    slug_override = final_url_slug if final_url_slug != base_url_slug else ""
    if slug_override:
        print(f"  Slug collision detected — using slug '{slug_override}'")

    activity_id = activity["id"]

    has_route = False
    if activity.get("has_latlng"):
        print("  Fetching route stream...")
        latlng = fetch_streams(session, activity_id)
        has_route = sp.save_route_geojson(latlng, post_dir)
        if has_route:
            print(f"  Saved route.geojson ({len(latlng)} points)")

    photo_items = []
    banner_filename = ""
    print("  Fetching photos...")
    photos = normalize_photos(fetch_photos(session, activity_id))
    if photos:
        banner_filename, banner_photo = sp.download_banner(photos, post_dir)
        non_banner = [p for p in photos if p is not banner_photo]
        if dl_photos:
            photo_items = sp.download_photos(non_banner, post_dir)
        else:
            photo_items = [p["urls"]["5000"] for p in non_banner]
        if banner_filename:
            photo_items = [banner_filename] + photo_items

    content = sp.build_post(activity, draft, use_miles, photo_items, has_route,
                            banner_filename, slug_override)
    (post_dir / "index.md").write_text(content, encoding="utf-8")
    return post_dir / "index.md"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert Strava activities into Zola blog posts using your "
                    "browser session cookie (no API access needed)."
    )
    parser.add_argument("--count", type=int, default=20,
                        help="Activities to show in picker (default: 20)")
    parser.add_argument("--draft", action="store_true", help="Mark posts as drafts")
    parser.add_argument("--download-photos", action="store_true",
                        help="Download photos locally instead of linking to CloudFront URLs")
    parser.add_argument("--all", action="store_true",
                        help="Create posts for all activities (skips existing)")
    parser.add_argument("--new", action="store_true",
                        help="Only show not-yet-posted activities (stops paging once "
                             "it reaches a page of already-posted ones)")
    args = parser.parse_args()

    session = get_session()

    if args.all:
        print("Fetching all activities...")
        selected = list_all_activities(session)
        if not selected:
            print("No activities found.")
            sys.exit(1)
        print(f"\nFound {len(selected)} activities. Creating posts (skipping existing)...")
    elif args.new:
        print("Fetching new (not-yet-posted) activities...")
        activities = list_new_activities(session)
        if not activities:
            print("All activities already have posts.")
            sys.exit(0)
        selected = sp.interactive_picker(activities)
    else:
        print(f"Fetching {args.count} recent activities...")
        activities = list_activities(session, args.count)
        if not activities:
            print("No activities found.")
            sys.exit(1)
        selected = sp.interactive_picker(activities)

    created, skipped = 0, 0
    for i, activity in enumerate(selected, 1):
        print(f"\n[{i}/{len(selected)}] {activity['start_date_local'][:10]} — {activity['name']}")
        post_file = create_post_web(session, activity, args.draft,
                                    args.download_photos, skip_existing=args.all)
        if post_file is None:
            print("  Skipped (already exists).")
            skipped += 1
        else:
            print(f"  Created: {post_file.relative_to(sp.REPO_ROOT)}")
            created += 1
        if len(selected) > 1:
            time.sleep(0.5)

    print("\nRebuilding routes.geojson...")
    sp.rebuild_routes_geojson()
    print(f"\nDone. Created {created}, skipped {skipped}.")
    if args.draft and created:
        print("Posts are marked as draft — remove 'draft = true' from front matter to publish.")


if __name__ == "__main__":
    main()
