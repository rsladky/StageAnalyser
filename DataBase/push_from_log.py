"""
Fallback / outil de dev : extrait les blocs JSON de runs du log debug d'Isaac
(marqueurs [StageAnalyserJSON]...[/StageAnalyserJSON]) et les importe via l'RPC
import_run. Utile si --luadebug n'est pas activé (pas d'upload direct depuis le mod).

Usage:
    python DataBase/push_from_log.py [chemin/vers/log.txt]
"""

import re
import sys
import json
from pathlib import Path
import import_to_db

MARK_START = "[StageAnalyserJSON]"
MARK_END = "[/StageAnalyserJSON]"


def extract_runs(log_text: str):
    pattern = re.compile(re.escape(MARK_START) + r"(.*?)" + re.escape(MARK_END), re.DOTALL)
    for match in pattern.finditer(log_text):
        json_str = match.group(1).strip()
        if not json_str:
            continue
        try:
            yield json.loads(json_str)
        except json.JSONDecodeError:
            continue


def import_from_log(log_path: Path):
    if not log_path.exists():
        sys.exit(f"Log file not found: {log_path}")

    text = log_path.read_text(encoding="utf-8", errors="ignore")
    runs = list(extract_runs(text))
    if not runs:
        print("No runs found in log.")
        return

    print(f"Found {len(runs)} run(s) in log, importing via RPC...")
    for idx, run_data in enumerate(runs, start=1):
        print(f"[{idx}/{len(runs)}]", end=" ")
        import_to_db.import_run_payload(run_data)


def main():
    default_log = Path(
        "~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/"
        "DBAA9250-ABEB-4E4F-A8A9-88D75693B4D4/drive_c/users/crossover/Documents/"
        "My Games/Binding of Isaac Repentance/log.txt"
    ).expanduser()
    log_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else default_log
    import_from_log(log_arg)


if __name__ == "__main__":
    main()
