#!/usr/bin/env python3
"""
backfill_banner_photos.py — One-off script to prepend banner.jpg to the
## Photos section of existing Strava posts that have a banner but don't
already list it in photos.

No API calls — purely local file edits.

Usage:
  python scripts/backfill_banner_photos.py          # dry run (preview only)
  python scripts/backfill_banner_photos.py --apply  # write changes
"""

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONTENT_DIR = REPO_ROOT / "content" / "strava"

BANNER_LINE = "![Activity photo](banner.jpg)"
PHOTOS_HEADER = "## Photos"


def process(index_md: Path, apply: bool) -> str | None:
    """Return a description of the change made/needed, or None if nothing to do."""
    post_dir = index_md.parent
    if not (post_dir / "banner.jpg").exists():
        return None

    text = index_md.read_text(encoding="utf-8")

    # Skip if banner already referenced in the file body (after front matter)
    front_end = text.find("+++", 3)
    body = text[front_end + 3:] if front_end != -1 else text
    if "banner.jpg" in body:
        return None

    if PHOTOS_HEADER in body:
        # Insert banner.jpg as first photo after the ## Photos heading
        new_body = body.replace(
            f"{PHOTOS_HEADER}\n\n",
            f"{PHOTOS_HEADER}\n\n{BANNER_LINE}\n\n",
            1,
        )
    else:
        # No photos section — append one before the end
        strava_link_pat = re.compile(r"(\[View on Strava\]\(https://www\.strava\.com/activities/\d+\))")
        m = strava_link_pat.search(body)
        if m:
            insert_after = m.end()
            new_body = body[:insert_after] + f"\n\n{PHOTOS_HEADER}\n\n{BANNER_LINE}\n" + body[insert_after:]
        else:
            new_body = body + f"\n{PHOTOS_HEADER}\n\n{BANNER_LINE}\n"

    if new_body == body:
        return None

    new_text = text[:front_end + 3] + new_body if front_end != -1 else new_body

    if apply:
        index_md.write_text(new_text, encoding="utf-8")
        return "updated"
    return "would update"


def main():
    parser = argparse.ArgumentParser(description="Backfill banner.jpg into Strava post photo lists.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    updated, skipped = 0, 0
    for index_md in sorted(CONTENT_DIR.rglob("index.md")):
        result = process(index_md, args.apply)
        if result:
            print(f"  {result}: {index_md.parent.name}")
            updated += 1
        else:
            skipped += 1

    action = "Updated" if args.apply else "Would update"
    print(f"\n{action} {updated} post(s), skipped {skipped}.")
    if not args.apply and updated:
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
