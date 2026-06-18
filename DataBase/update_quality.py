"""
Parse un quality dump du log debug d'Isaac et peuple les catalogues d'items
(Name + Quality) dans Supabase via upsert.

Usage:
    python DataBase/update_quality.py [log_path]

Le log doit contenir un bloc délimité par :
    [QualityDump:START] ... [QualityDump:END]
avec des lignes de la forme :
    [QualityDump] id=<n> quality=<0-4> type=<n> name=<...>

Types d'items Isaac :
    1 = Passif (collectible)  → PassiveItem
    3 = Actif  (collectible)  → ActiveItem
    4 = Familier (passif)     → PassiveItem
"""

import os
import re
import sys
from pathlib import Path
from supabase import create_client, Client

# Charger .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

DEFAULT_LOG_PATHS = [
    Path(
        "~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/"
        "DBAA9250-ABEB-4E4F-A8A9-88D75693B4D4/drive_c/users/crossover/Documents/"
        "My Games/Binding of Isaac Repentance/log.txt"
    ).expanduser(),
    Path.home() / "Documents/My Games/Binding of Isaac Repentance/log.txt",
]

LINE_RE = re.compile(r"\[QualityDump\] id=(\d+) quality=(\d+) type=(\d+) name=(.*)")


def find_log_path(override=None):
    if override:
        return Path(override)
    for p in DEFAULT_LOG_PATHS:
        if p.exists():
            return p
    sys.exit(
        "Could not find Isaac log. Pass the path as an argument:\n"
        "  python DataBase/update_quality.py /path/to/log.txt"
    )


def parse_dump(log_path):
    """Extrait id→(quality, type, name) du dernier bloc QualityDump du log."""
    text = log_path.read_text(encoding="utf-8", errors="replace")

    start = text.rfind("[QualityDump:START]")
    end = text.rfind("[QualityDump:END]")
    if start == -1 or end == -1 or end < start:
        sys.exit("No complete [QualityDump:START]...[QualityDump:END] block found in log.")

    block = text[start:end]
    items = {}
    for m in LINE_RE.finditer(block):
        item_id = int(m.group(1))
        quality = int(m.group(2))
        item_type = int(m.group(3))
        name = m.group(4).strip()
        items[item_id] = (quality, item_type, name)

    print(f"Parsed {len(items)} items from quality dump.")
    return items


def update_qualities(items: dict, supabase: Client):
    passive_rows, active_rows, skipped = [], [], 0

    for item_id, (quality, item_type, name) in items.items():
        row = {"id": item_id, "Name": name or None, "Quality": quality}
        if item_type in (1, 4):
            passive_rows.append(row)
        elif item_type == 3:
            active_rows.append(row)
        else:
            skipped += 1

    if passive_rows:
        supabase.table("PassiveItem").upsert(passive_rows).execute()
    if active_rows:
        supabase.table("ActiveItem").upsert(active_rows).execute()

    print(f"\n✓ Upserted {len(passive_rows)} passive items, {len(active_rows)} active items.")
    if skipped:
        print(f"  Skipped {skipped} items with unrecognised type.")


if __name__ == "__main__":
    log_path = find_log_path(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Reading log: {log_path}")

    items = parse_dump(log_path)
    if not items:
        sys.exit("No items parsed — check the log contains a complete dump block.")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    update_qualities(items, supabase)
