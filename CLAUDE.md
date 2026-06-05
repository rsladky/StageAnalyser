# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StageAnalyser is a two-layer Binding of Isaac: Repentance mod that collects granular gameplay data and stores it in Supabase.

**Data flow:** Isaac Game → Lua mod (collects data) → game debug log (JSON markers) → `push_from_log.py` (extracts) → `import_to_db.py` (normalizes & imports) → Supabase

## Running the Python Backend

```bash
# Activate virtual environment
source .venv/bin/activate

# Extract from the game log and import to Supabase
python DataBase/push_from_log.py
# or with a custom log path:
python DataBase/push_from_log.py /path/to/log.txt

# Import a specific JSON run file interactively
python DataBase/import_to_db.py

# Test Supabase connection and RLS permissions
python test_supabase.py
```

Credentials and config are loaded from `.env`:
- `SUPABASE_URL`, `SUPABASE_KEY` — required
- `PLAYER_NAME` — username to associate runs with (default: `"Player1"`)

Deduplication state is stored in `DataBase/.imported_hashes` — delete this file to force re-import of all runs.

## Architecture

### Lua Layer (`main.lua` + `resources/scripts/`)

- **`main.lua`** — registers the mod and hooks 5 Isaac callbacks, delegating everything to `DataCollector`
- **`data_collector.lua`** — core engine; maintains `runData` (runs → floors → rooms → player states); serializes to JSON and writes to the debug log wrapped in `[StageAnalyserJSON]...[/StageAnalyserJSON]` markers; also persists via `Isaac.SaveModData()`
- **`utils.lua`** and **`callbacks.lua`** — currently unused helpers

### Python Layer (`DataBase/`)

- **`push_from_log.py`** — regex-extracts JSON blocks from the Isaac debug log, writes them to temp files, and calls `import_to_db.import_run_to_database()`
- **`import_to_db.py`** — normalizes and inserts run data into Supabase tables: `User`, `Run`, `Stage`, `Room`, `RoomMonster`, `PlayerState`, `Inventory`; uses in-memory caching to avoid redundant lookups; handles Supabase RLS errors with a fallback to user ID 1

### Supabase Schema (inferred)

`User` → `Run` → `Stage` → `Room` → `RoomMonster`  
`Run` → `PlayerState` → `Inventory` (items, trinkets, consumables)

## Lua Conventions

- Stage names and room type names are hardcoded maps in `data_collector.lua` (8 stages × up to 6 variants including Repentance alt-paths, 28 room types)
- The mod targets the Isaac API available in Repentance; use `Isaac.*`, `Game():Get*()`, and entity iteration patterns consistent with the existing code
- JSON serialization uses Isaac's built-in `require("json")` from `resources/scripts/json.lua` — don't add external libraries
- The JSON output includes `health`, `stats`, and `consumables` fields that have no DB columns — they're kept for local debugging but not imported

## JSON Fields Emitted by the Lua Mod

Key non-obvious fields:
- `rooms[].bosses` — array of `{type, variant, subType}` for boss entities; only populated in Boss rooms (type 5)
- `rooms[].enterFrame` / `rooms[].clearedFrame` — game frame counts when the room was entered/cleared; Python uses wall-clock time for `Room.ClearTime`
- `startTime` — game frame count at run start, **not** a Unix timestamp
- `items.active` — only the first slot is stored in DB (`PlayerState.Id_Activ_Item`); Schoolbag second slot is silently dropped
- `trinkets` — only the first trinket is stored in DB (`PlayerState.id_Trinket`)
