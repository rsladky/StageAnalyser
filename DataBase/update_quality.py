"""
Parse a quality dump from the Isaac debug log and update the Quality column
in Passive_Item and Activ_Item tables in Supabase.

Usage:
    python DataBase/update_quality.py [log_path]

The log must contain a block delimited by:
    [QualityDump:START] ... [QualityDump:END]
with lines of the form:
    [QualityDump] id=<n> quality=<0-4> type=<n> name=<...>

Item types in Isaac:
    1 = Passive collectible  → Passive_Item
    3 = Active collectible   → Activ_Item
    4 = Familiar (passive)   → Passive_Item
"""

import os
import re
import sys
from pathlib import Path
from supabase import create_client, Client

# Load .env
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
    Path.home()
    / "~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/DBAA9250-ABEB-4E4F-A8A9-88D75693B4D4/drive_c/users/crossover/Documents/My\ Games/Binding\ of\ Isaac\ Repentance/log.txt",
    Path.home() / "Documents/My Games/Binding of Isaac Repentance/log.txt",
]

LINE_RE = re.compile(r"\[QualityDump\] id=(\d+) quality=(\d+) type=(\d+)")


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
    """Extract id→(quality, type) from the last QualityDump block in the log."""
    text = log_path.read_text(encoding="utf-8", errors="replace")

    # Find the last complete dump block
    start = text.rfind("[QualityDump:START]")
    end = text.rfind("[QualityDump:END]")
    if start == -1 or end == -1 or end < start:
        sys.exit(
            "No complete [QualityDump:START]...[QualityDump:END] block found in log."
        )

    block = text[start:end]
    items = {}
    for m in LINE_RE.finditer(block):
        item_id = int(m.group(1))
        quality = int(m.group(2))
        item_type = int(m.group(3))
        items[item_id] = (quality, item_type)

    print(f"Parsed {len(items)} items from quality dump.")
    return items


def update_qualities(items: dict, supabase: Client):
    passive_updates = 0
    active_updates = 0
    skipped = 0

    for item_id, (quality, item_type) in items.items():
        # type 1 = passive, type 4 = familiar (also in Passive_Item)
        if item_type in (1, 4):
            table = "Passive_Item"
        elif item_type == 3:
            table = "Activ_Item"
        else:
            skipped += 1
            continue

        try:
            result = (
                supabase.table(table)
                .update({"Quality": quality})
                .eq("id", item_id)
                .execute()
            )
            if result.data:
                if table == "Passive_Item":
                    passive_updates += 1
                else:
                    active_updates += 1
        except Exception as e:
            print(f"  ✗ Failed to update {table} id={item_id}: {e}")

    print(
        f"\n✓ Updated {passive_updates} passive items, {active_updates} active items."
    )
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
