#!/usr/bin/env python3
"""
strava_to_post.py — Convert Strava activities into Zola blog posts.

Usage:
  python scripts/strava_to_post.py                        # interactive picker
  python scripts/strava_to_post.py --count 30             # show more activities
  python scripts/strava_to_post.py --activity-id 12345    # direct by ID
  python scripts/strava_to_post.py --activity-id 12345 --draft
  python scripts/strava_to_post.py --all                  # all activities since beginning
  python scripts/strava_to_post.py --all --draft          # all as drafts
  python scripts/strava_to_post.py --rebuild-only         # rebuild static/strava/routes.geojson from existing content
"""

import argparse
import json
import os
import re
import sys
import time
import tomllib
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_FILE = SCRIPT_DIR / ".strava_config.json"
CONTENT_DIR = REPO_ROOT / "content" / "strava"
STATIC_DIR = REPO_ROOT / "static"

# ---------------------------------------------------------------------------
# Strava API constants
# ---------------------------------------------------------------------------

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
API_BASE = "https://www.strava.com/api/v3"
REDIRECT_URI = "http://localhost:8765/callback"
SCOPE = "activity:read_all"

PACE_SPORT_TYPES = {
    "Run", "TrailRun", "VirtualRun", "Walk", "Hike",
    "BackcountrySkiing", "NordicSki",
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    CONFIG_FILE.chmod(0o600)


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def get_access_token(config: dict) -> str:
    """Return a valid access token, refreshing if needed."""
    if config.get("expires_at", 0) > time.time() + 60:
        return config["access_token"]

    print("Access token expired, refreshing...")
    resp = requests.post(TOKEN_URL, data={
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": config["refresh_token"],
    })
    resp.raise_for_status()
    data = resp.json()
    config["access_token"] = data["access_token"]
    config["refresh_token"] = data["refresh_token"]
    config["expires_at"] = data["expires_at"]
    save_config(config)
    print("Token refreshed.")
    return config["access_token"]


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

class _OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            _OAuthHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;padding:2em">
                <h2>Authorization successful!</h2>
                <p>You can close this tab and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing code parameter")

    def log_message(self, *args):
        pass  # suppress server logs


def run_oauth_flow(config: dict) -> None:
    """Open browser, capture auth code via local server, exchange for tokens."""
    params = urlencode({
        "client_id": config["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
    })
    url = f"{AUTH_URL}?{params}"

    print(f"\nOpening browser for Strava authorization...")
    print(f"If the browser doesn't open, visit:\n  {url}\n")
    webbrowser.open(url)

    server = HTTPServer(("localhost", 8765), _OAuthHandler)
    print("Waiting for authorization callback on http://localhost:8765/callback ...")
    while _OAuthHandler.auth_code is None:
        server.handle_request()
    server.server_close()

    code = _OAuthHandler.auth_code
    print("Authorization code received, exchanging for tokens...")

    resp = requests.post(TOKEN_URL, data={
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()

    config["access_token"] = data["access_token"]
    config["refresh_token"] = data["refresh_token"]
    config["expires_at"] = data["expires_at"]
    # Store athlete preferences for unit conversion
    athlete = data.get("athlete", {})
    config["measurement_preference"] = athlete.get("measurement_preference", "meters")
    save_config(config)
    print("Tokens saved.\n")


def ensure_auth(config: dict) -> dict:
    """Prompt for credentials and run OAuth if not already configured."""
    if not config.get("client_id"):
        print("No Strava credentials found.")
        print("Create an API application at https://www.strava.com/settings/api")
        print("Set the Authorization Callback Domain to: localhost\n")
        config["client_id"] = input("Enter your Client ID: ").strip()
        config["client_secret"] = input("Enter your Client Secret: ").strip()

    if not config.get("access_token"):
        run_oauth_flow(config)
    else:
        get_access_token(config)  # refresh if needed, saves updated config

    return config


# ---------------------------------------------------------------------------
# Strava API calls
# ---------------------------------------------------------------------------

def api_get(token: str, path: str, params: dict = None) -> dict | list:
    for attempt in range(5):
        resp = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("X-RateLimit-Reset", 900))
            wait = min(retry_after, 900)
            print(f"  Rate limited. Waiting {wait}s before retrying...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def list_activities(token: str, count: int = 20) -> list:
    return api_get(token, "/athlete/activities", {"per_page": count})


def list_all_activities(token: str) -> list:
    """Fetch every activity by paginating until the API returns an empty page."""
    all_activities = []
    page = 1
    per_page = 200  # Strava's maximum
    while True:
        print(f"  Fetching page {page} ({per_page} per page)...")
        batch = api_get(token, "/athlete/activities", {"per_page": per_page, "page": page})
        if not batch:
            break
        all_activities.extend(batch)
        print(f"  Got {len(batch)} activities (total so far: {len(all_activities)})")
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(0.5)  # be polite to the API
    return all_activities


def get_activity(token: str, activity_id: int) -> dict:
    return api_get(token, f"/activities/{activity_id}")


def get_athlete(token: str) -> dict:
    return api_get(token, "/athlete")


def get_activity_streams(token: str, activity_id: int) -> list:
    """Return latlng stream as [[lat, lon], ...], or [] if unavailable."""
    try:
        data = api_get(token, f"/activities/{activity_id}/streams",
                       {"keys": "latlng", "key_by_type": "true"})
        # Response is a list of stream objects; find the latlng one
        if isinstance(data, list):
            for stream in data:
                if stream.get("type") == "latlng":
                    return stream.get("data", [])
        elif isinstance(data, dict):
            latlng = data.get("latlng") or {}
            return latlng.get("data", [])
    except requests.HTTPError:
        pass
    return []


def save_route_geojson(latlng: list, post_dir: Path) -> bool:
    """Write route.geojson as a GeoJSON LineString. Returns True if written."""
    if not latlng:
        return False
    # Strava gives [lat, lon]; GeoJSON needs [lon, lat]
    coordinates = [[lon, lat] for lat, lon in latlng]
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {},
        }],
    }
    (post_dir / "route.geojson").write_text(
        json.dumps(geojson, separators=(",", ":")), encoding="utf-8"
    )
    return True


def get_activity_photos(token: str, activity_id: int) -> list:
    try:
        return api_get(token, f"/activities/{activity_id}/photos",
                       {"photo_sources": "true", "size": 5000})
    except requests.HTTPError:
        return []


def download_banner(photos: list, post_dir: Path) -> str:
    """Download the default/feature photo as banner.jpg. Returns 'banner.jpg' or ''."""
    primary = next((p for p in photos if p.get("default_photo")), photos[0] if photos else None)
    if not primary:
        return ""
    urls = primary.get("urls") or {}
    url = urls.get("5000") or urls.get("600") or urls.get("100")
    if not url:
        return ""
    print("  Downloading banner (feature photo)...")
    resp = requests.get(url)
    resp.raise_for_status()
    (post_dir / "banner.jpg").write_bytes(resp.content)
    return "banner.jpg"


def download_photos(photos: list, post_dir: Path) -> list:
    """Download photos into post_dir. Returns list of local filenames."""
    filenames = []
    for i, photo in enumerate(photos, 1):
        urls = photo.get("urls") or {}
        url = urls.get("5000") or urls.get("600") or urls.get("100")
        if not url:
            continue
        ext = Path(urlparse(url).path).suffix or ".jpg"
        filename = f"photo_{i}{ext}"
        print(f"  Downloading photo {i}/{len(photos)}...")
        resp = requests.get(url)
        resp.raise_for_status()
        (post_dir / filename).write_bytes(resp.content)
        filenames.append(filename)
    return filenames


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------

def parse_selection(raw: str, max_n: int) -> list[int] | None:
    """Parse a selection string like '1-4,6,8-9' into a sorted list of 1-based indices.
    Returns None if the input is invalid."""
    indices = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            if not (bounds[0].isdigit() and bounds[1].isdigit()):
                return None
            lo, hi = int(bounds[0]), int(bounds[1])
            if lo < 1 or hi > max_n or lo > hi:
                return None
            indices.update(range(lo, hi + 1))
        elif part.isdigit():
            n = int(part)
            if n < 1 or n > max_n:
                return None
            indices.add(n)
        else:
            return None
    return sorted(indices) if indices else None


def interactive_picker(activities: list) -> list[dict]:
    """Show a numbered list of activities and return the selected summaries.
    Accepts ranges like '1-4,6,8-9'. Returns a list (single or multiple)."""
    print(f"\n{'#':>3}  {'Name':<35} {'Date':<12} {'Distance':>9}  {'Type'}")
    print("-" * 75)
    for i, a in enumerate(activities, 1):
        date = a.get("start_date_local", "")[:10]
        dist_m = a.get("distance", 0)
        dist = f"{dist_m / 1000:.1f} km" if dist_m else "—"
        name = a.get("name", "")[:34]
        sport = a.get("sport_type", a.get("type", ""))
        print(f"{i:>3}. {name:<35} {date:<12} {dist:>9}  {sport}")

    print()
    while True:
        raw = input(f"Select activities [1-{len(activities)}, ranges like 1-4,6,8-9]: ").strip()
        indices = parse_selection(raw, len(activities))
        if indices:
            return [activities[i - 1] for i in indices]
        print(f"  Invalid selection. Use numbers or ranges like '1-4,6,8-9'.")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_duration(seconds: int) -> str:
    if not seconds:
        return "—"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def fmt_pace(meters_per_second: float, use_miles: bool) -> str:
    """Return pace as MM:SS /km or /mi."""
    if not meters_per_second or meters_per_second <= 0:
        return "—"
    unit_dist = 1609.34 if use_miles else 1000.0
    seconds_per_unit = unit_dist / meters_per_second
    m = int(seconds_per_unit // 60)
    s = int(seconds_per_unit % 60)
    unit = "mi" if use_miles else "km"
    return f"{m}:{s:02d} /{unit}"


def fmt_speed(meters_per_second: float, use_miles: bool) -> str:
    if not meters_per_second:
        return "—"
    if use_miles:
        return f"{meters_per_second * 2.23694:.1f} mph"
    return f"{meters_per_second * 3.6:.1f} km/h"


def fmt_distance(meters: float, use_miles: bool) -> str:
    if not meters:
        return "—"
    if use_miles:
        return f"{meters / 1609.34:.2f} mi"
    return f"{meters / 1000:.2f} km"


def fmt_elevation(meters: float, use_miles: bool) -> str:
    if meters is None:
        return "—"
    if use_miles:
        return f"{meters * 3.28084:.0f} ft"
    return f"{meters:.0f} m"


def toml_escape(s: str) -> str:
    """Escape a string for use inside a TOML basic string (double-quoted)."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# ---------------------------------------------------------------------------
# Routes GeoJSON helpers
# ---------------------------------------------------------------------------

def parse_front_matter(index_md: Path) -> dict:
    """Parse TOML front matter from a Zola content file (between +++ markers)."""
    text = index_md.read_text(encoding="utf-8")
    match = re.match(r"^\+\+\+\n(.*?)\n\+\+\+", text, re.DOTALL)
    if not match:
        return {}
    try:
        return tomllib.loads(match.group(1))
    except Exception:
        return {}


def rebuild_routes_geojson() -> None:
    """Rebuild static/strava/routes.geojson from all content/strava/*/route.geojson files."""
    features = []
    for activity_dir in sorted(CONTENT_DIR.iterdir()):
        if not activity_dir.is_dir():
            continue
        route_file = activity_dir / "route.geojson"
        index_file = activity_dir / "index.md"
        if not (route_file.exists() and index_file.exists()):
            continue

        try:
            route_data = json.loads(route_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        fm = parse_front_matter(index_file)
        if not fm:
            continue

        slug = activity_dir.name
        # Zola strips YYYY-MM-DD- date prefixes from directory slugs
        url_slug = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', slug)
        name = fm.get("title", slug)
        date = str(fm.get("date", ""))
        sport_type = ((fm.get("taxonomies") or {}).get("tags") or ["Activity"])[0]
        banner = (fm.get("extra") or {}).get("banner", "")
        banner_url = f"/strava/{url_slug}/{banner}" if banner else ""
        url = f"/strava/{url_slug}/"

        coords = None
        for feature in route_data.get("features", []):
            geom = feature.get("geometry", {})
            if geom.get("type") == "LineString":
                coords = geom.get("coordinates")
                break
        if not coords:
            continue

        extra = fm.get("extra") or {}
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "name": name,
                "sport_type": sport_type,
                "date": date,
                "url": url,
                "banner_url": banner_url,
                "distance": extra.get("distance_fmt", ""),
                "moving_time": extra.get("moving_time_fmt", ""),
                "elevation": extra.get("elevation_gain_fmt", ""),
            },
        })

    out_path = STATIC_DIR / "strava" / "routes.geojson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  Rebuilt routes.geojson ({len(features)} route(s))")


# ---------------------------------------------------------------------------
# Post generation
# ---------------------------------------------------------------------------

def build_post(activity: dict, draft: bool, use_miles: bool, photo_items: list = None, has_route: bool = False, banner_filename: str = "") -> str:
    sport_type = activity.get("sport_type") or activity.get("type", "Activity")
    name = activity.get("name", "Untitled Activity")
    description = (activity.get("description") or "").strip()
    start_local = activity.get("start_date_local", "")
    date_str = start_local[:10] if start_local else datetime.now().strftime("%Y-%m-%d")
    activity_id = activity.get("id", "")

    # Gear
    gear = activity.get("gear") or {}
    gear_name = gear.get("name") if gear else None

    # Location
    location_parts = [
        activity.get("location_city"),
        activity.get("location_state"),
        activity.get("location_country"),
    ]
    location = ", ".join(p for p in location_parts if p) or None

    # Speed/pace
    avg_speed = activity.get("average_speed")
    max_speed = activity.get("max_speed")
    use_pace = sport_type in PACE_SPORT_TYPES

    # Pre-compute stats for front matter and table
    distance_fmt = fmt_distance(activity.get("distance"), use_miles)
    moving_time_fmt = fmt_duration(activity.get("moving_time"))
    elevation_gain_fmt = fmt_elevation(activity.get("total_elevation_gain"), use_miles)

    # --- Front matter ---
    lines = ["+++"]
    lines.append(f'title = "{toml_escape(name)}"')
    lines.append(f'description = "{toml_escape(sport_type)} — {date_str}"')
    lines.append(f"date = {date_str}")
    lines.append('authors = ["Max Katz-Christy"]')
    if draft:
        lines.append("draft = true")
    lines.append("")
    lines.append("[taxonomies]")
    lines.append(f'tags = ["{toml_escape(sport_type)}"]')
    lines.append("")
    lines.append("[extra]")
    lines.append(f'banner = "{toml_escape(banner_filename)}"')
    lines.append(f"strava_id = {activity_id}")
    lines.append(f'distance_fmt = "{toml_escape(distance_fmt)}"')
    lines.append(f'moving_time_fmt = "{toml_escape(moving_time_fmt)}"')
    lines.append(f'elevation_gain_fmt = "{toml_escape(elevation_gain_fmt)}"')
    lines.append("+++")
    lines.append("")

    # --- Description ---
    if description:
        lines.append(description)
        lines.append("")

    # --- Stats table ---
    lines.append("## Stats")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")

    def row(label, value):
        if value and value != "—":
            lines.append(f"| **{label}** | {value} |")

    row("Distance", distance_fmt)
    row("Moving time", moving_time_fmt)
    row("Elapsed time", fmt_duration(activity.get("elapsed_time")))
    row("Elevation gain", elevation_gain_fmt)

    if use_pace:
        row("Average pace", fmt_pace(avg_speed, use_miles))
        row("Best pace", fmt_pace(max_speed, use_miles))
    else:
        row("Average speed", fmt_speed(avg_speed, use_miles))
        row("Max speed", fmt_speed(max_speed, use_miles))

    if activity.get("average_cadence"):
        row("Average cadence", f"{activity['average_cadence']:.0f} rpm")
    if activity.get("average_heartrate"):
        row("Average heart rate", f"{activity['average_heartrate']:.0f} bpm")
    if activity.get("max_heartrate"):
        row("Max heart rate", f"{activity['max_heartrate']:.0f} bpm")
    if activity.get("average_watts"):
        row("Average power", f"{activity['average_watts']:.0f} W")
    if activity.get("weighted_average_watts"):
        row("Weighted avg power", f"{activity['weighted_average_watts']:.0f} W")
    if activity.get("kilojoules"):
        row("Energy", f"{activity['kilojoules']:.0f} kJ")
    if activity.get("calories"):
        row("Calories", f"{activity['calories']:.0f} kcal")
    if activity.get("achievement_count"):
        row("Achievements", str(activity["achievement_count"]))
    if gear_name:
        row("Gear", gear_name)
    if activity.get("device_name"):
        row("Device", activity["device_name"])
    if location:
        row("Location", location)

    lines.append("")

    # --- Map ---
    lines.append("## Route")
    lines.append("")
    if has_route:
        lines.append("{{ strava_map() }}")
        lines.append("")
    lines.append(f"[View on Strava](https://www.strava.com/activities/{activity_id})")
    lines.append("")

    # --- Photos ---
    if photo_items:
        lines.append("## Photos")
        lines.append("")
        for item in photo_items:
            lines.append(f"![Activity photo]({item})")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post creation
# ---------------------------------------------------------------------------

def create_post(activity: dict, draft: bool, use_miles: bool, token: str, dl_photos: bool = False, skip_existing: bool = False) -> Path | None:
    start_local = activity.get("start_date_local", "")
    date_str = start_local[:10] if start_local else datetime.now().strftime("%Y-%m-%d")
    name = activity.get("name", "activity")
    slug = f"{date_str}-{slugify(name)}"
    post_dir = CONTENT_DIR / slug

    if post_dir.exists():
        if skip_existing:
            return None
        ans = input(f"\nDirectory '{post_dir}' already exists. Overwrite? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            sys.exit(0)
    else:
        post_dir.mkdir(parents=True)

    activity_id = activity.get("id")

    # Download route
    has_route = False
    polyline = (activity.get("map") or {}).get("summary_polyline") or ""
    if polyline and activity_id:
        print("Fetching route stream...")
        latlng = get_activity_streams(token, activity_id)
        has_route = save_route_geojson(latlng, post_dir)
        if has_route:
            print(f"  Saved route.geojson ({len(latlng)} points)")

    # Photos — activity.photo_count is unreliable; use photos.count instead
    photo_items = []   # local filenames (downloaded) or CloudFront URLs
    banner_filename = ""
    photo_count = (activity.get("photos") or {}).get("count", 0)
    if photo_count > 0 and activity_id:
        print(f"Fetching {photo_count} photo(s)...")
        photos = get_activity_photos(token, activity_id)
        if photos:
            banner_filename = download_banner(photos, post_dir)
            non_banner = [p for p in photos if not p.get("default_photo")]
            if dl_photos:
                photo_items = download_photos(non_banner, post_dir)
            else:
                for p in non_banner:
                    urls = p.get("urls") or {}
                    url = urls.get("5000") or urls.get("600") or urls.get("100")
                    if url:
                        photo_items.append(url)

    content = build_post(activity, draft, use_miles, photo_items, has_route, banner_filename)
    post_file = post_dir / "index.md"
    post_file.write_text(content, encoding="utf-8")

    print("Rebuilding routes.geojson...")
    rebuild_routes_geojson()

    return post_file


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert a Strava activity into a Zola blog post."
    )
    parser.add_argument("--activity-id", type=int, help="Strava activity ID")
    parser.add_argument("--count", type=int, default=20, help="Activities to show in picker (default: 20)")
    parser.add_argument("--draft", action="store_true", help="Mark post as draft")
    parser.add_argument("--download-photos", action="store_true",
                        help="Download photos locally instead of linking to CloudFront URLs")
    parser.add_argument("--all", action="store_true",
                        help="Fetch and create posts for all activities since the beginning (skips existing)")
    parser.add_argument("--rebuild-only", action="store_true",
                        help="Rebuild static/strava/routes.geojson from existing content, then exit")
    args = parser.parse_args()

    if args.rebuild_only:
        print("Rebuilding routes.geojson from existing content...")
        rebuild_routes_geojson()
        return

    config = load_config()
    config = ensure_auth(config)
    token = get_access_token(config)

    # Determine units
    if not config.get("measurement_preference"):
        try:
            athlete = get_athlete(token)
            config["measurement_preference"] = athlete.get("measurement_preference", "meters")
            save_config(config)
        except Exception:
            config["measurement_preference"] = "meters"
    use_miles = config.get("measurement_preference") == "feet"

    # Get activity / activities
    if args.all:
        print("Fetching all activities from Strava...")
        summaries = list_all_activities(token)
        if not summaries:
            print("No activities found.")
            sys.exit(1)
        print(f"\nFound {len(summaries)} activities total. Creating posts (skipping existing)...\n")
        created, skipped = 0, 0
        for i, summary in enumerate(summaries, 1):
            date_str = summary.get("start_date_local", "")[:10]
            name = summary.get("name", "activity")
            print(f"[{i}/{len(summaries)}] {date_str} — {name}")
            slug = f"{date_str}-{slugify(name)}"
            if (CONTENT_DIR / slug).exists():
                print("  Skipped (already exists).")
                skipped += 1
                continue
            print(f"  Fetching full details...")
            try:
                activity = get_activity(token, summary["id"])
                post_file = create_post(activity, args.draft, use_miles, token, args.download_photos, skip_existing=True)
                if post_file is None:
                    print("  Skipped (already exists).")
                    skipped += 1
                else:
                    print(f"  Created: {post_file.relative_to(REPO_ROOT)}")
                    created += 1
                time.sleep(10)  # stay under rate limits (~3 req/activity, limit is 100/15min)
            except Exception as e:
                print(f"  ERROR: {e}")
        print(f"\nDone. Created {created}, skipped {skipped} existing.")
    elif args.activity_id:
        print(f"Fetching activity {args.activity_id}...")
        activity = get_activity(token, args.activity_id)
        post_file = create_post(activity, args.draft, use_miles, token, args.download_photos)
        print(f"\nCreated: {post_file.relative_to(REPO_ROOT)}")
        if args.draft:
            print("Post is marked as draft — remove 'draft = true' from front matter to publish.")
    else:
        print(f"Fetching {args.count} recent activities...")
        summaries = list_activities(token, args.count)
        if not summaries:
            print("No activities found.")
            sys.exit(1)
        selected = interactive_picker(summaries)
        for summary in selected:
            print(f"\nFetching full details for: {summary['name']}...")
            activity = get_activity(token, summary["id"])
            post_file = create_post(activity, args.draft, use_miles, token, args.download_photos)
            print(f"Created: {post_file.relative_to(REPO_ROOT)}")
        if args.draft:
            print("\nPosts are marked as draft — remove 'draft = true' from front matter to publish.")


if __name__ == "__main__":
    main()
