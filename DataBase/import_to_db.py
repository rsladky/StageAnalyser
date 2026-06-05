import hashlib
import json
import os
import sys
from datetime import datetime
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

# Configuration Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xbhbdzsqxilwfigxdnuq.supabase.co")

# Essayer d'utiliser la SERVICE ROLE KEY en priorité, sinon utiliser la clé anon
SUPABASE_KEY = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhiaGJkenNxeGlsd2ZpZ3hkbnVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkzOTYzNDgsImV4cCI6MjA4NDk3MjM0OH0.DASpyqZMkNWSbMTYn6_CyA8rWzbJMeAYfnlABL97RPs"))

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Supabase URL/KEY manquants. Définis SUPABASE_URL et SUPABASE_KEY (ou SUPABASE_ANON_KEY).")

PLAYER_NAME = os.getenv("PLAYER_NAME", "Player1")

HASHES_FILE = Path(__file__).parent / ".imported_hashes"

def _load_imported_hashes():
    if HASHES_FILE.exists():
        return set(HASHES_FILE.read_text().splitlines())
    return set()

def _record_imported_hash(h):
    with open(HASHES_FILE, "a") as f:
        f.write(h + "\n")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Cache pour les lookups (évite requêtes répétées)
_stage_type_cache = {}
_room_type_cache = {}
_item_cache = {}
_trinket_cache = {}
_boss_cache = {}

def import_run_to_database(json_file_path):
    """
    Importe une run depuis un fichier JSON vers la base de données Supabase
    """
    print(f"\n📥 Importing run from: {json_file_path}")

    # Charger les données JSON
    try:
        raw = Path(json_file_path).read_text(encoding='utf-8')
        run_data = json.loads(raw)
    except Exception as e:
        print(f"✗ Failed to parse JSON: {e}")
        return None

    # Deduplication: skip runs we've already imported
    run_hash = hashlib.sha256(raw.encode()).hexdigest()
    imported = _load_imported_hashes()
    if run_hash in imported:
        print(f"⏭  Run already imported (hash {run_hash[:8]}…), skipping.")
        return None
    
    print(f"📊 Run data summary:")
    print(f"   Seed: {run_data.get('seed', 'Unknown')}")
    print(f"   Character: {run_data.get('character', 'Unknown')}")
    print(f"   Floors: {len(run_data.get('floors', []))}")
    print(f"   Victory: {run_data.get('victory', False)}")
    print(f"   Duration: {run_data.get('duration', 0)}s")
    
    run_id = None
    try:
        # 1. Créer ou récupérer l'utilisateur
        user_id = get_or_create_user(PLAYER_NAME)
        if not user_id:
            print("✗ Failed to get/create user")
            return None
        
        # 2. Créer la run
        run_id = create_run(user_id, run_data)
        if not run_id:
            print("✗ Failed to create run")
            return None
        
        print(f"\n✓ Created run ID: {run_id}")
        
        # 3. Pour chaque floor
        total_rooms = 0
        total_player_states = 0
        
        for floor_idx, floor_data in enumerate(run_data.get('floors', []), 1):
            stage_name = floor_data.get('stageName', 'Unknown')
            num_rooms = len(floor_data.get('rooms', []))
            num_player_states = len(floor_data.get('playerStates', []))
            
            print(f"\n  📍 Floor {floor_idx}: {stage_name}")
            print(f"     Stage #{floor_data.get('stageNumber')} (type: {floor_data.get('stageType')})")
            
            floor_id = create_floor(run_id, floor_data)
            if not floor_id:
                print(f"     ✗ Failed to create floor")
                continue
            
            print(f"     ✓ Floor ID: {floor_id}")
            
            # 4. Pour chaque room du floor
            # Map roomIndex (JSON) -> DB id, so PlayerState can reference the correct room
            room_index_to_db_id = {}
            for room_idx, room_data in enumerate(floor_data.get('rooms', []), 1):
                room_id = create_room(run_id, floor_id, room_data)
                if room_id:
                    room_index_to_db_id[room_data.get('roomIndex')] = room_id
                    room_type = room_data.get('roomTypeName', 'Unknown')
                    num_enemies = len(room_data.get('enemies', []))
                    print(f"       🚪 Room {room_idx}: {room_type} (ID: {room_id}, enemies: {num_enemies})")

                    # Ennemis
                    for enemy_idx, enemy in enumerate(room_data.get('enemies', []), 1):
                        monster_id = create_room_monster(room_id, enemy)
                        if monster_id:
                            print(f"          👹 Enemy {enemy_idx}: type={enemy.get('type')}, variant={enemy.get('variant')}")

                    # Bosses
                    for boss in room_data.get('bosses', []):
                        boss_id = get_or_create_boss(boss.get('type', 0), boss.get('variant', 0))
                        if boss_id:
                            create_room_boss(room_id, boss_id)

                    total_rooms += 1

            # 5. Pour chaque player state
            for state_idx, player_state in enumerate(floor_data.get('playerStates', []), 1):
                state_id = create_player_state(run_id, floor_id, room_index_to_db_id, player_state)
                if state_id:
                    items = player_state.get('items', {})
                    num_passive = len(items.get('passive', []))
                    num_active = len(items.get('active', []))
                    num_trinkets = len(player_state.get('trinkets', []))
                    print(f"       👤 PlayerState {state_idx} (ID: {state_id}, items: {num_passive}p+{num_active}a+{num_trinkets}t)")
                    total_player_states += 1
        
        print(f"\n✓ Run {run_id} imported successfully!")
        print(f"   📊 Summary: {total_rooms} rooms, {total_player_states} player states")
        _record_imported_hash(run_hash)
        return run_id

    except Exception as e:
        print(f"✗ Error importing run: {e}")
        import traceback
        traceback.print_exc()
        if run_id:
            print(f"  🧹 Cleaning up partial import for run {run_id}...")
            cleanup_run(run_id)
        return None

def get_or_create_user(username):
    """Récupère un utilisateur existant ou en crée un nouveau"""
    try:
        # Chercher l'utilisateur par nom
        result = supabase.table('User').select('id').eq('Name', username).execute()
        
        if result.data and len(result.data) > 0:
            user_id = result.data[0]['id']
            print(f"  Found existing user: {username} (ID: {user_id})")
            return user_id
        
        # Essayer de créer un nouvel utilisateur
        try:
            result = supabase.table('User').insert({'Name': username}).execute()
            if result.data and len(result.data) > 0:
                user_id = result.data[0]['id']
                print(f"  Created new user: {username} (ID: {user_id})")
                return user_id
        except Exception as create_err:
            error_msg = str(create_err).lower()
            # Si création échoue (RLS), utiliser user ID 1 par défaut
            if "row-level security" in error_msg or "42501" in error_msg:
                print(f"  ⚠️  RLS blocks user creation, using default user (ID: 1)")
                print(f"     💡 Pour modifier users, use SUPABASE_KEY=<SERVICE_ROLE_KEY>")
                return 1
            raise
        
        return None
    except Exception as e:
        print(f"Error in get_or_create_user: {e}")
        return None

def create_run(user_id, run_data):
    """Crée une run dans la BDD"""
    try:
        # startTime is a game frame count, not a Unix epoch — let Supabase auto-populate created_at
        run_insert = {
            'id_User': user_id
        }
        
        result = supabase.table('Run').insert(run_insert).execute()
        if result.data and len(result.data) > 0:
            run_id = result.data[0]['id']
            print(f"  ✓ Created run in DB (ID: {run_id}, seed: {run_data.get('seed', 'N/A')})")
            return run_id
        print(f"  ✗ Failed to insert run: {result}")
        return None
    except Exception as e:
        print(f"  ✗ Error creating run: {e}")
        return None

def get_stage_type_id(stage_name):
    """Récupère ou crée un type de stage par nom"""
    if stage_name in _stage_type_cache:
        return _stage_type_cache[stage_name]
    
    try:
        # Chercher le stage type
        result = supabase.table('StageType').select('id').eq('Type', stage_name).execute()
        
        if result.data and len(result.data) > 0:
            stage_id = result.data[0]['id']
            _stage_type_cache[stage_name] = stage_id
            return stage_id
        
        # Créer s'il n'existe pas
        result = supabase.table('StageType').insert({'Type': stage_name}).execute()
        if result.data and len(result.data) > 0:
            stage_id = result.data[0]['id']
            _stage_type_cache[stage_name] = stage_id
            return stage_id
        
        return None
    except Exception as e:
        print(f"Error getting stage type: {e}")
        return None

def create_floor(run_id, floor_data):
    """Crée un floor (Stage) dans la BDD"""
    try:
        # Récupérer ou créer le StageType
        stage_name = floor_data.get('stageName', 'Unknown')
        stage_type_id = get_stage_type_id(stage_name)
        if not stage_type_id:
            print(f"       ✗ Failed to get/create stage type: {stage_name}")
            return None
        
        floor_insert = {
            'id_Run': run_id,
            'id_StageType': stage_type_id
        }
        
        result = supabase.table('Stage').insert(floor_insert).execute()
        if result.data and len(result.data) > 0:
            floor_id = result.data[0]['id']
            return floor_id
        print(f"       ✗ Failed to insert stage: {result}")
        return None
    except Exception as e:
        print(f"       ✗ Error creating floor: {e}")
        return None

def get_room_type_id(room_type_name):
    """Récupère ou crée un type de room par nom"""
    if room_type_name in _room_type_cache:
        return _room_type_cache[room_type_name]
    
    try:
        # Chercher le room type
        result = supabase.table('RoomType').select('id').eq('Type', room_type_name).execute()
        
        if result.data and len(result.data) > 0:
            room_id = result.data[0]['id']
            _room_type_cache[room_type_name] = room_id
            return room_id
        
        # Créer s'il n'existe pas
        result = supabase.table('RoomType').insert({'Type': room_type_name}).execute()
        if result.data and len(result.data) > 0:
            room_id = result.data[0]['id']
            _room_type_cache[room_type_name] = room_id
            return room_id
        
        return None
    except Exception as e:
        print(f"Error getting room type: {e}")
        return None

def create_room(run_id, floor_id, room_data):
    """Crée une room dans la BDD"""
    try:
        # Récupérer le RoomType
        room_type_name = room_data.get('roomTypeName', 'Unknown')
        room_type_id = get_room_type_id(room_type_name)
        if not room_type_id:
            print(f"         ✗ Failed to get/create room type: {room_type_name}")
            return None
        
        # ClearTime: use wall-clock import time when the room was cleared in-game
        clear_time = datetime.now().isoformat() if room_data.get('clearedFrame') is not None else None

        room_insert = {
            'id_Run': run_id,
            'id_Floor': floor_id,
            'id_RoomType': room_type_id,
            'ClearTime': clear_time
        }
        
        result = supabase.table('Room').insert(room_insert).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        print(f"         ✗ Failed to insert room: {result}")
        return None
    except Exception as e:
        print(f"         ✗ Error creating room: {e}")
        return None

def get_passive_item_id(game_item_id):
    """Récupère l'ID d'un item passif par son ID du jeu"""
    cache_key = f"passive_{game_item_id}"
    if cache_key in _item_cache:
        return _item_cache[cache_key]
    
    try:
        # Chercher l'item par son ID du jeu (on suppose que l'ID du jeu = ID en BDD)
        result = supabase.table('Passive_Item').select('id').eq('id', game_item_id).execute()
        
        if result.data and len(result.data) > 0:
            item_id = result.data[0]['id']
            _item_cache[cache_key] = item_id
            return item_id
        
        return None
    except Exception as e:
        print(f"Error getting passive item {game_item_id}: {e}")
        return None

def get_active_item_id(game_item_id):
    """Récupère l'ID d'un item actif par son ID du jeu"""
    cache_key = f"active_{game_item_id}"
    if cache_key in _item_cache:
        return _item_cache[cache_key]
    
    try:
        # Chercher l'item par son ID du jeu
        result = supabase.table('Activ_Item').select('id').eq('id', game_item_id).execute()
        
        if result.data and len(result.data) > 0:
            item_id = result.data[0]['id']
            _item_cache[cache_key] = item_id
            return item_id
        
        return None
    except Exception as e:
        print(f"Error getting active item {game_item_id}: {e}")
        return None

def get_trinket_id(game_trinket_id):
    """Récupère l'ID d'un trinket par son ID du jeu"""
    if game_trinket_id in _trinket_cache:
        return _trinket_cache[game_trinket_id]
    
    try:
        # Chercher le trinket par son ID du jeu
        result = supabase.table('Trinket').select('id').eq('id', game_trinket_id).execute()
        
        if result.data and len(result.data) > 0:
            trinket_id = result.data[0]['id']
            _trinket_cache[game_trinket_id] = trinket_id
            return trinket_id
        
        return None
    except Exception as e:
        print(f"Error getting trinket {game_trinket_id}: {e}")
        return None

def create_player_state(run_id, floor_id, room_index_to_db_id, player_state):
    """Crée un état du joueur dans la BDD"""
    try:
        # Récupérer l'item actif (schema stores only one)
        active_item_id = None
        if player_state.get('items', {}).get('active'):
            active_item_id = get_active_item_id(player_state['items']['active'][0]['id'])

        # Récupérer le trinket — schema stores only one (PlayerState.id_Trinket)
        trinket_id = None
        if player_state.get('trinkets'):
            trinket_id = get_trinket_id(player_state['trinkets'][0])

        # Resolve the DB room id from the player state's roomIndex
        room_id = room_index_to_db_id.get(player_state.get('roomIndex')) if room_index_to_db_id else None
        
        player_state_insert = {
            'id_Run': run_id,
            'id_Floor': floor_id,
            'id_Room': room_id,
            'Id_Activ_Item': active_item_id,
            'id_Trinket': trinket_id
        }
        
        result = supabase.table('PlayerState').insert(player_state_insert).execute()
        if not result.data:
            print(f"           ✗ Failed to insert player state: {result}")
            return None
        
        player_state_id = result.data[0]['id']

        # Note: health, stats, and consumables are collected by Lua but have no DB columns
        passive_items = player_state.get('items', {}).get('passive', [])
        
        # Créer les entrées d'inventaire pour les items passifs
        inventory_count = 0
        for passive_item in passive_items:
            item_game_id = passive_item['id']
            if create_inventory_entry(player_state_id, item_game_id):
                inventory_count += 1
        
        return player_state_id
    except Exception as e:
        print(f"           ✗ Error creating player state: {e}")
        return None

def create_inventory_entry(player_state_id, item_id):
    """Crée une entrée d'inventaire"""
    try:
        passive_item_id = get_passive_item_id(item_id)
        if not passive_item_id:
            return None
        
        inventory_insert = {
            'id_PlayerState': player_state_id,
            'id_Passive_Item': passive_item_id
        }
        
        result = supabase.table('Inventory').insert(inventory_insert).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return None
    except Exception as e:
        return None

def create_room_monster(room_id, enemy):
    """Crée une relation RoomMonster pour les ennemis"""
    try:
        monster_type = enemy.get('type', 0)
        monster_variant = enemy.get('variant', 0)
        monster_id = get_or_create_monster(monster_type, monster_variant)
        if not monster_id:
            return None
        
        room_monster_insert = {
            'id_Room': room_id,
            'id_Monster': monster_id
        }
        
        result = supabase.table('RoomMonster').insert(room_monster_insert).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return None
    except Exception as e:
        return None

def get_or_create_monster(monster_type, variant):
    """Récupère ou crée un monstre par type et variant"""
    try:
        # Chercher le monstre
        result = supabase.table('Monster').select('id').eq('Type', float(monster_type)).eq('IdMonstre', variant).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        
        # Créer le monstre
        monster_insert = {
            'Type': float(monster_type),
            'IdMonstre': variant
        }
        result = supabase.table('Monster').insert(monster_insert).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        
        return None
    except Exception as e:
        print(f"Error getting/creating monster: {e}")
        return None

def cleanup_run(run_id):
    """Delete all records for a partially-imported run, in reverse dependency order."""
    try:
        rooms = supabase.table('Room').select('id').eq('id_Run', run_id).execute().data or []
        room_ids = [r['id'] for r in rooms]
        player_states = supabase.table('PlayerState').select('id').eq('id_Run', run_id).execute().data or []
        ps_ids = [ps['id'] for ps in player_states]

        for ps_id in ps_ids:
            supabase.table('Inventory').delete().eq('id_PlayerState', ps_id).execute()
        supabase.table('PlayerState').delete().eq('id_Run', run_id).execute()

        for room_id in room_ids:
            supabase.table('RoomMonster').delete().eq('id_Room', room_id).execute()
            supabase.table('RoomBoss').delete().eq('id_Room', room_id).execute()
        supabase.table('Room').delete().eq('id_Run', run_id).execute()

        supabase.table('Stage').delete().eq('id_Run', run_id).execute()
        supabase.table('Run').delete().eq('id', run_id).execute()
        print(f"  ✓ Cleanup complete for run {run_id}")
    except Exception as e:
        print(f"  ✗ Cleanup failed for run {run_id}: {e}")

def get_or_create_boss(boss_type, variant):
    """Récupère ou crée un boss par type et variant"""
    cache_key = (boss_type, variant)
    if cache_key in _boss_cache:
        return _boss_cache[cache_key]

    try:
        name = f"Boss_{boss_type}_{variant}"
        result = supabase.table('Boss').select('id').eq('Name', name).execute()
        if result.data and len(result.data) > 0:
            boss_id = result.data[0]['id']
            _boss_cache[cache_key] = boss_id
            return boss_id

        result = supabase.table('Boss').insert({'Name': name}).execute()
        if result.data and len(result.data) > 0:
            boss_id = result.data[0]['id']
            _boss_cache[cache_key] = boss_id
            return boss_id

        return None
    except Exception as e:
        print(f"Error getting/creating boss {boss_type}/{variant}: {e}")
        return None

def create_room_boss(room_id, boss_id):
    """Crée une relation RoomBoss"""
    try:
        result = supabase.table('RoomBoss').insert({'id_Room': room_id, 'id_Boss': boss_id}).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]['id']
        return None
    except Exception as e:
        print(f"Error creating RoomBoss: {e}")
        return None

def import_all_runs_from_directory(directory_path):
    """Importe toutes les runs d'un répertoire"""
    json_files = [f for f in os.listdir(directory_path) if f.endswith('.json') and f.startswith('stageanalyser_')]
    
    print(f"Found {len(json_files)} run files to import")
    
    for json_file in json_files:
        file_path = os.path.join(directory_path, json_file)
        import_run_to_database(file_path)

if __name__ == "__main__":
    # Exemple d'utilisation
    print("=== Isaac Run Data Importer ===")
    print("\nConfiguration:")
    print(f"Supabase URL: {SUPABASE_URL}")
    print("\nOptions:")
    print("1. Import single run")
    print("2. Import all runs from directory")
    
    choice = input("\nSelect option: ")
    
    if choice == "1":
        file_path = input("Enter JSON file path: ")
        import_run_to_database(file_path)
    elif choice == "2":
        directory = input("Enter directory path: ")
        import_all_runs_from_directory(directory)
    else:
        print("Invalid choice")
