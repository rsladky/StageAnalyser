"""
Test end-to-end de la fonction import_run sans lancer le jeu.
Envoie une run synthétique, vérifie la cascade + les colonnes calculées,
et teste la déduplication. La run de test est taguée playerId='test-harness'.

    python DataBase/test_import.py
"""

import os
from pathlib import Path
from supabase import create_client

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

RUN = {
    "runID": 111,
    "playerId": "test-harness",
    "seed": "TEST00000000",
    "startTime": 100,
    "character": 0,
    "difficulty": 1,
    "endTime": 5100,
    "victory": True,
    "duration": 5000,
    "floors": [
        {
            "floorID": 100,
            "stageNumber": 1,
            "stageType": 0,
            "stageName": "Basement",
            "curses": 0,
            "rooms": [
                {
                    "roomIndex": 0, "roomType": 1, "roomTypeName": "Normal",
                    "visited": True, "cleared": True,
                    "enemies": [], "bosses": [],
                    "enterFrame": 100, "clearedFrame": 100, "timestamp": 100,
                },
                {
                    "roomIndex": 84, "roomType": 5, "roomTypeName": "Boss",
                    "visited": True, "cleared": True,
                    "enemies": [
                        {"type": 19, "variant": 0, "subType": 0, "hp": 50.0, "maxHp": 60.0},
                        {"type": 19, "variant": 0, "subType": 0, "hp": 10.0, "maxHp": 60.0},
                    ],
                    "bosses": [{"type": 19, "variant": 0, "subType": 0}],
                    "enterFrame": 2000, "clearedFrame": 2450, "timestamp": 2000,
                },
            ],
            "playerStates": [
                {
                    "timestamp": 100, "roomIndex": 0,
                    "health": {"hearts": 6, "maxHearts": 6, "soulHearts": 0,
                               "blackHearts": 0, "boneHearts": 0, "goldenHearts": 0},
                    "stats": {"damage": 3.5, "tears": 10.0, "speed": 1.0,
                              "range": 6.5, "shotSpeed": 1.0, "luck": 0.0},
                    "items": {"passive": [{"id": 1, "count": 1}], "active": []},
                    "trinkets": [], "consumables": {"coins": 0, "bombs": 1, "keys": 1},
                },
                {
                    "timestamp": 2000, "roomIndex": 84,
                    "health": {"hearts": 4, "maxHearts": 6, "soulHearts": 2,
                               "blackHearts": 0, "boneHearts": 0, "goldenHearts": 0},
                    "stats": {"damage": 5.0, "tears": 9.0, "speed": 1.0,
                              "range": 7.0, "shotSpeed": 1.1, "luck": 1.0},
                    "items": {"passive": [{"id": 1, "count": 1}, {"id": 114, "count": 1}],
                              "active": [{"id": 33, "charge": 6}]},
                    "trinkets": [2, 5],
                    "consumables": {"coins": 3, "bombs": 0, "keys": 2},
                },
            ],
        }
    ],
}


def count(table, run_id):
    return len(sb.table(table).select("id").eq("id_run", run_id).execute().data)


print("→ Appel import_run …")
run_id = sb.rpc("import_run", {"payload": RUN}).execute().data
print(f"   Run id = {run_id}")

print("\n→ Cascade :")
print(f"   Stage        : {count('Stage', run_id)}  (attendu 1)")
print(f"   Room         : {count('Room', run_id)}  (attendu 2)")
print(f"   PlayerState  : {count('PlayerState', run_id)}  (attendu 2)")

room = sb.table("Room").select("RoomTypeName,ClearDurationFrames").eq("id_run", run_id).order("id").execute().data
print(f"\n→ Rooms : {room}")

ps = sb.table("PlayerState").select("Frame,Hearts,SoulHearts,DamageTaken").eq("id_run", run_id).order("Frame").execute().data
print(f"→ PlayerStates (DamageTaken attendu: 1er=null/0, 2e=0 car 6 → 4+2=6) : {ps}")

ps_ids = [r["id"] for r in sb.table("PlayerState").select("id").eq("id_run", run_id).execute().data]
inv = sb.table("Inventory").select("id").in_("id_playerstate", ps_ids).execute().data
act = sb.table("PlayerStateActive").select("id").in_("id_playerstate", ps_ids).execute().data
tri = sb.table("PlayerStateTrinket").select("id").in_("id_playerstate", ps_ids).execute().data
print(f"\n→ Inventory={len(inv)} (attendu 3)  Active={len(act)} (attendu 1)  Trinkets={len(tri)} (attendu 2)")

room_ids = [r["id"] for r in sb.table("Room").select("id").eq("id_run", run_id).execute().data]
rm = sb.table("RoomMonster").select("id").in_("id_room", room_ids).execute().data
rb = sb.table("RoomBoss").select("id").in_("id_room", room_ids).execute().data
print(f"→ RoomMonster={len(rm)} (attendu 2)  RoomBoss={len(rb)} (attendu 1)")

print("\n→ Test déduplication (2e appel identique) …")
run_id2 = sb.rpc("import_run", {"payload": RUN}).execute().data
print(f"   Run id = {run_id2}  →  {'OK (même id, pas de doublon)' if run_id2 == run_id else 'ÉCHEC dédup !'}")

print(f"\nPour nettoyer la run de test : supprime l'utilisateur 'test-harness' "
      f"(Run id {run_id}) côté Supabase.")
