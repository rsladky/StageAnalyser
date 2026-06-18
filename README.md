# StageAnalyser

Mod **The Binding of Isaac: Repentance** qui collecte des données de gameplay très
granulaires (étages, rooms, état du joueur à chaque room) et les envoie à une base
**Supabase**, en vue d'analyser **les variables qui impactent la difficulté d'une run**.

## Flux de données

```
Jeu Isaac → mod Lua → curl POST (rpc import_run) → Supabase   (upload automatique)
                   ↘ log debug [StageAnalyserJSON] → push_from_log.py → Supabase   (fallback)
```

Le mod sérialise chaque run en JSON et l'envoie directement à la fonction Postgres
`import_run(jsonb)`, qui normalise et déduplique les données côté serveur. Si l'upload
direct n'est pas disponible, le JSON reste dans le log et peut être poussé manuellement.

## ⚠️ Activer l'upload automatique : `--luadebug`

Le Lua d'Isaac est **sandboxé** : il ne peut accéder au réseau qu'avec le flag de
lancement `--luadebug`. Pour que le mod envoie les runs tout seul :

1. Steam → clic droit sur *The Binding of Isaac: Rebirth* → **Propriétés**.
2. **Options de lancement** → ajouter `--luadebug`.
3. `curl` doit être disponible (présent par défaut sur Windows 10+, macOS, Linux).

> Sécurité : `--luadebug` lève le bac à sable Lua. La clé Supabase embarquée est la clé
> **anon** publique, restreinte en **insert-only** (voir RLS plus bas) — elle ne peut que
> contribuer des runs, jamais lire ni modifier la base.

Sans `--luadebug`, le mod fonctionne quand même : les runs sont écrites dans le log et
importables via `push_from_log.py`.

## Mise en place de la base (Supabase)

1. Dans l'éditeur SQL Supabase, exécuter **`DataBase/schema.sql`** (recrée toutes les
   tables, la fonction `import_run` et les permissions RLS insert-only).
2. (Optionnel mais recommandé) peupler le catalogue d'items avec leur qualité :
   ```bash
   source .venv/bin/activate
   python DataBase/update_quality.py        # nécessite une clé SERVICE_ROLE dans .env
   ```
   Le mod émet un *quality dump* dans le log au premier lancement.

## Backend Python (fallback / dev)

```bash
source .venv/bin/activate

# Pousser les runs trouvées dans le log debug vers Supabase (via l'RPC import_run)
python DataBase/push_from_log.py
# ou avec un chemin de log personnalisé :
python DataBase/push_from_log.py /chemin/vers/log.txt

# Importer un fichier JSON de run précis
python DataBase/import_to_db.py

# Tester la connexion Supabase
python test_supabase.py
```

Configuration via `.env` :
- `SUPABASE_URL` — URL du projet
- `SUPABASE_KEY` (ou `SUPABASE_ANON_KEY`) — clé **anon** pour l'import (RPC), ou
  **service_role** pour les scripts d'admin comme `update_quality.py`

La déduplication est gérée côté serveur (`Run.RunHash`).

## Architecture

### Couche Lua (`main.lua` + `resources/scripts/`)
- **`main.lua`** — enregistre le mod et branche 5 callbacks Isaac, délègue à `DataCollector`.
- **`data_collector.lua`** — moteur de collecte (runs → floors → rooms → playerStates),
  capture stats / vie / inventaire / consommables / ennemis / malédictions / mode de
  difficulté ; génère un `contributorId` persistant ; sérialise en JSON.
- **`uploader.lua`** — POST du JSON vers `rpc/import_run` via `curl` (si `--luadebug`).
- **`dump_qualities.lua`** — dump unique des qualités d'items vers le log.

### Couche serveur (`DataBase/schema.sql`)
- 15 tables analytiques (`Run`, `Stage`, `Room`, `PlayerState`, `Inventory`,
  `PlayerStateActive`, `PlayerStateTrinket`, `RoomMonster`, `RoomBoss`, catalogues…),
  une table d'audit `RawRun`, et la fonction `import_run(jsonb)` (SECURITY DEFINER) qui
  fait toute la normalisation + le calcul des features dérivées
  (`DamageTaken`, `ClearDurationFrames`).
- **RLS insert-only** : accès tables révoqué pour `anon`/`authenticated` ; seule la fonction
  `import_run` leur est accordée.

### Couche Python (`DataBase/`)
- **`push_from_log.py`** — extrait les blocs JSON du log et appelle l'RPC.
- **`import_to_db.py`** — mince wrapper de l'RPC `import_run`.
- **`update_quality.py`** — peuple `PassiveItem`/`ActiveItem` (Name + Quality) depuis le dump.

## Variables de difficulté collectées

- **Labels** : dégâts subis par room (`PlayerState.DamageTaken`), durée de clear in-game
  (`Room.ClearDurationFrames`), issue de run (`Run.Victory` / `Duration`).
- **Features joueur** : stats (damage, tears, shotSpeed, range, speed, luck), 6 types de
  cœurs, inventaire (passifs + Quality, actifs + charge, trinkets), consommables.
- **Features menace** : hp/type des ennemis, boss, type de room, profondeur d'étage
  (numéro + variante alt-path), malédictions, mode de difficulté.
