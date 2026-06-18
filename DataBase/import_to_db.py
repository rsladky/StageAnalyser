"""
Import d'une run vers Supabase.

La normalisation (Run → Stage → Room → PlayerState → ...) est désormais faite
côté serveur par la fonction Postgres `import_run(jsonb)` (voir DataBase/schema.sql).
Ce module n'est plus qu'un mince wrapper : il envoie le JSON brut de la run à l'RPC.
La déduplication est gérée côté serveur (Run.RunHash).
"""

import json
import os
import sys
from pathlib import Path
from supabase import create_client, Client

# Charger .env s'il existe
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xbhbdzsqxilwfigxdnuq.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY"))

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Supabase URL/KEY manquants. Définis SUPABASE_URL et SUPABASE_KEY (ou SUPABASE_ANON_KEY).")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def import_run_payload(run_data: dict):
    """Envoie un dict de run à la fonction RPC import_run. Retourne l'id de Run ou None."""
    seed = run_data.get("seed", "?")
    floors = len(run_data.get("floors", []))
    print(f"📥 import_run  seed={seed}  floors={floors}  victory={run_data.get('victory')}")
    try:
        result = supabase.rpc("import_run", {"payload": run_data}).execute()
        run_id = result.data
        print(f"   ✓ Run id {run_id}")
        return run_id
    except Exception as e:
        print(f"   ✗ RPC import_run a échoué : {e}")
        return None


def import_run_to_database(json_file_path):
    """Charge un fichier JSON de run et l'importe via l'RPC."""
    print(f"\n📂 {json_file_path}")
    try:
        run_data = json.loads(Path(json_file_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"✗ JSON illisible : {e}")
        return None
    return import_run_payload(run_data)


def import_all_runs_from_directory(directory_path):
    json_files = [
        f for f in os.listdir(directory_path)
        if f.endswith(".json") and f.startswith("stageanalyser_")
    ]
    print(f"Found {len(json_files)} run files to import")
    for json_file in json_files:
        import_run_to_database(os.path.join(directory_path, json_file))


if __name__ == "__main__":
    print("=== Isaac Run Data Importer (RPC import_run) ===")
    print(f"Supabase URL: {SUPABASE_URL}")
    print("\n1. Import single run\n2. Import all runs from directory")
    choice = input("\nSelect option: ")
    if choice == "1":
        import_run_to_database(input("Enter JSON file path: "))
    elif choice == "2":
        import_all_runs_from_directory(input("Enter directory path: "))
    else:
        print("Invalid choice")
