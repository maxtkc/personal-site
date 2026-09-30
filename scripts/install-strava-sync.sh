#!/usr/bin/env bash
# Installs the strava-sync systemd user timer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"

mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR/systemd/strava-sync.service" "$UNIT_DIR/strava-sync.service"
cp "$SCRIPT_DIR/systemd/strava-sync.timer" "$UNIT_DIR/strava-sync.timer"

systemctl --user daemon-reload
systemctl --user enable --now strava-sync.timer

echo
echo "Installed. Next scheduled run:"
systemctl --user list-timers strava-sync.timer
