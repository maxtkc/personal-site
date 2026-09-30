#!/usr/bin/env bash
# Fetches new Strava activities, creates posts for any that are missing,
# and commits/pushes them to main. Meant to run unattended (systemd timer).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[strava-sync] $(date -Is) starting"

python3 scripts/strava_web_to_post.py --all

if git status --porcelain content/strava static/strava/routes.geojson | grep -q .; then
    git add content/strava static/strava/routes.geojson
    git commit -m "Add Strava post(s): $(date +%Y-%m-%d)"
    git push origin main
    echo "[strava-sync] $(date -Is) pushed new post(s)"
else
    echo "[strava-sync] $(date -Is) no new activities"
fi
