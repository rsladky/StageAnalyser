import hashlib
import re
import sys
import json
import tempfile
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
            data = json.loads(json_str)
            yield data
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

    print(f"Found {len(runs)} run(s) in log, importing...")

    for idx, run_data in enumerate(runs, start=1):
        json_str = json.dumps(run_data)
        run_hash = hashlib.sha256(json_str.encode()).hexdigest()

        # Skip early if already imported (mirrors the check inside import_to_db)
        if run_hash in import_to_db._load_imported_hashes():
            print(f"[{idx}/{len(runs)}] Already imported (hash {run_hash[:8]}…), skipping.")
            continue

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            tmp.write(json_str)
            tmp_path = tmp.name
        try:
            import_to_db.import_run_to_database(tmp_path)
            print(f"[{idx}/{len(runs)}] Imported run")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

def main():
    default_log = Path("~/Library/Containers/com.isaacmarovitz.Whisky/Bottles/DBAA9250-ABEB-4E4F-A8A9-88D75693B4D4/drive_c/users/crossover/Documents/My Games/Binding of Isaac Repentance/log.txt").expanduser()
    log_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else default_log
    import_from_log(log_arg)

if __name__ == "__main__":
    main()
