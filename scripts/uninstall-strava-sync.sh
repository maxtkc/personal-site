#!/usr/bin/env bash
# Removes the strava-sync systemd user timer.
set -euo pipefail

UNIT_DIR="$HOME/.config/systemd/user"

systemctl --user disable --now strava-sync.timer 2>/dev/null || true
rm -f "$UNIT_DIR/strava-sync.service" "$UNIT_DIR/strava-sync.timer"
systemctl --user daemon-reload

echo "Uninstalled."
