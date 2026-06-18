-- StageAnalyser — schéma BDD complet pour l'analyse de difficulté.
-- À exécuter dans l'éditeur SQL Supabase. Recrée entièrement la base.
--
-- Flux : le mod (ou push_from_log.py) appelle la fonction `import_run(jsonb)`
-- avec le JSON brut d'une run. La normalisation + déduplication est faite
-- côté serveur, dans une transaction. La clé anon ne peut QUE appeler
-- import_run (insert-only) ; aucun accès direct aux tables.

-- ============================================================================
-- 0. DROP (ordre inverse des dépendances)
-- ============================================================================
drop function if exists public.import_run(jsonb) cascade;

drop table if exists public."Inventory" cascade;
drop table if exists public."PlayerStateActive" cascade;
drop table if exists public."PlayerStateTrinket" cascade;
drop table if exists public."RoomMonster" cascade;
drop table if exists public."RoomBoss" cascade;
drop table if exists public."PlayerState" cascade;
drop table if exists public."Room" cascade;
drop table if exists public."Stage" cascade;
drop table if exists public."Run" cascade;
drop table if exists public."RawRun" cascade;
drop table if exists public."Monster" cascade;
drop table if exists public."Boss" cascade;
drop table if exists public."PassiveItem" cascade;
drop table if exists public."ActiveItem" cascade;
drop table if exists public."Trinket" cascade;
drop table if exists public."User" cascade;
-- anciennes tables remplacées
drop table if exists public."StageType" cascade;
drop table if exists public."RoomType" cascade;
drop table if exists public."Activ_Item" cascade;
drop table if exists public."Passive_Item" cascade;

-- ============================================================================
-- 1. Catalogues
-- ============================================================================
create table public."User" (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  "Name"      text unique
);

-- Items : id = ID du jeu (pas une identity) pour que les FK soient triviales.
create table public."PassiveItem" (
  id            bigint primary key,
  "Name"        text,
  "Quality"     bigint,
  "Description"  text
);

create table public."ActiveItem" (
  id            bigint primary key,
  "Name"        text,
  "Quality"     bigint,
  "Description"  text
);

create table public."Trinket" (
  id            bigint primary key,
  "Name"        text,
  "Quality"     bigint,
  "Description"  text
);

create table public."Monster" (
  id            bigint generated always as identity primary key,
  "Type"        real,
  "Variant"     bigint,
  "Name"        text,
  "Description"  text,
  unique ("Type", "Variant")
);

create table public."Boss" (
  id            bigint generated always as identity primary key,
  "Type"        bigint,
  "Variant"     bigint,
  "Name"        text,
  unique ("Type", "Variant")
);

-- ============================================================================
-- 2. Archive brute (audit / repro)
-- ============================================================================
create table public."RawRun" (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  payload     jsonb not null,
  run_hash    text,
  status      text default 'imported'
);

-- ============================================================================
-- 3. Données analytiques
-- ============================================================================
create table public."Run" (
  id           bigint generated always as identity primary key,
  created_at   timestamptz not null default now(),
  id_User      bigint references public."User"(id),
  "Seed"       text,
  "Character"  bigint,
  "Difficulty" bigint,
  "Victory"    boolean,
  "StartFrame" bigint,
  "EndFrame"   bigint,
  "Duration"   bigint,
  "RunHash"    text unique
);

create table public."Stage" (
  id             bigint generated always as identity primary key,
  created_at     timestamptz not null default now(),
  id_Run         bigint references public."Run"(id),
  "StageNumber"  bigint,
  "StageVariant" bigint,
  "StageName"    text,
  "Curses"       bigint,
  "FloorFrame"   bigint
);

create table public."Room" (
  id                    bigint generated always as identity primary key,
  created_at            timestamptz not null default now(),
  id_Run                bigint references public."Run"(id),
  id_Stage              bigint references public."Stage"(id),
  "RoomIndex"           bigint,
  "RoomType"            bigint,
  "RoomTypeName"        text,
  "EnterFrame"          bigint,
  "ClearedFrame"        bigint,
  "ClearDurationFrames" bigint,
  "Cleared"             boolean
);

create table public."PlayerState" (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  id_Run        bigint references public."Run"(id),
  id_Stage      bigint references public."Stage"(id),
  id_Room       bigint references public."Room"(id),
  "Frame"       bigint,
  "Damage"      real,
  "FireDelay"   real,
  "ShotSpeed"   real,
  "TearRange"   real,
  "MoveSpeed"   real,
  "Luck"        real,
  "Hearts"      bigint,
  "MaxHearts"   bigint,
  "SoulHearts"  bigint,
  "BlackHearts" bigint,
  "BoneHearts"  bigint,
  "GoldenHearts" bigint,
  "Coins"       bigint,
  "Bombs"       bigint,
  "Keys"        bigint,
  "DamageTaken" bigint
);

create table public."Inventory" (
  id              bigint generated always as identity primary key,
  id_PlayerState  bigint references public."PlayerState"(id),
  id_PassiveItem  bigint references public."PassiveItem"(id),
  "Count"         bigint
);

create table public."PlayerStateActive" (
  id              bigint generated always as identity primary key,
  id_PlayerState  bigint references public."PlayerState"(id),
  id_ActiveItem   bigint references public."ActiveItem"(id),
  "Charge"        bigint,
  "Slot"          bigint
);

create table public."PlayerStateTrinket" (
  id              bigint generated always as identity primary key,
  id_PlayerState  bigint references public."PlayerState"(id),
  id_Trinket      bigint references public."Trinket"(id),
  "Slot"          bigint
);

create table public."RoomMonster" (
  id          bigint generated always as identity primary key,
  id_Room     bigint references public."Room"(id),
  id_Monster  bigint references public."Monster"(id),
  "SubType"   bigint,
  "Hp"        real,
  "MaxHp"     real
);

create table public."RoomBoss" (
  id        bigint generated always as identity primary key,
  id_Room   bigint references public."Room"(id),
  id_Boss   bigint references public."Boss"(id),
  "SubType" bigint
);

-- ============================================================================
-- 4. Fonction d'import (normalisation côté serveur, atomique)
-- ============================================================================
create or replace function public.import_run(payload jsonb)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  v_hash        text;
  v_run_id      bigint;
  v_user_id     bigint;
  v_user_name   text;
  v_stage_id    bigint;
  v_room_id     bigint;
  v_ps_id       bigint;
  v_monster_id  bigint;
  v_boss_id     bigint;
  v_floor       jsonb;
  v_room        jsonb;
  v_enemy       jsonb;
  v_boss        jsonb;
  v_ps          jsonb;
  v_item        jsonb;
  v_active      jsonb;
  v_trinket     jsonb;
  v_idx         int;
  v_room_map    jsonb := '{}'::jsonb;  -- roomIndex(text) -> Room.id
  v_clear_dur   bigint;
begin
  -- Déduplication : md5 du payload normalisé
  v_hash := md5(payload::text);

  select id into v_run_id from public."Run" where "RunHash" = v_hash;
  if v_run_id is not null then
    return v_run_id;  -- déjà importé
  end if;

  insert into public."RawRun"(payload, run_hash) values (payload, v_hash);

  -- Utilisateur : playerId fourni par le mod, sinon 'Anonymous'
  v_user_name := coalesce(payload->>'playerId', payload->>'playerName', 'Anonymous');
  select id into v_user_id from public."User" where "Name" = v_user_name;
  if v_user_id is null then
    insert into public."User"("Name") values (v_user_name) returning id into v_user_id;
  end if;

  -- Run
  insert into public."Run"(
    id_User, "Seed", "Character", "Difficulty", "Victory",
    "StartFrame", "EndFrame", "Duration", "RunHash"
  ) values (
    v_user_id,
    payload->>'seed',
    (payload->>'character')::bigint,
    (payload->>'difficulty')::bigint,
    (payload->>'victory')::boolean,
    (payload->>'startTime')::bigint,
    (payload->>'endTime')::bigint,
    (payload->>'duration')::bigint,
    v_hash
  ) returning id into v_run_id;

  -- Étages
  for v_floor in select * from jsonb_array_elements(coalesce(payload->'floors', '[]'::jsonb))
  loop
    insert into public."Stage"(
      id_Run, "StageNumber", "StageVariant", "StageName", "Curses", "FloorFrame"
    ) values (
      v_run_id,
      (v_floor->>'stageNumber')::bigint,
      (v_floor->>'stageType')::bigint,
      v_floor->>'stageName',
      (v_floor->>'curses')::bigint,
      (v_floor->>'floorID')::bigint
    ) returning id into v_stage_id;

    v_room_map := '{}'::jsonb;

    -- Rooms
    for v_room in select * from jsonb_array_elements(coalesce(v_floor->'rooms', '[]'::jsonb))
    loop
      v_clear_dur := null;
      if (v_room->>'clearedFrame') is not null and (v_room->>'enterFrame') is not null then
        v_clear_dur := (v_room->>'clearedFrame')::bigint - (v_room->>'enterFrame')::bigint;
      end if;

      insert into public."Room"(
        id_Run, id_Stage, "RoomIndex", "RoomType", "RoomTypeName",
        "EnterFrame", "ClearedFrame", "ClearDurationFrames", "Cleared"
      ) values (
        v_run_id, v_stage_id,
        (v_room->>'roomIndex')::bigint,
        (v_room->>'roomType')::bigint,
        v_room->>'roomTypeName',
        (v_room->>'enterFrame')::bigint,
        (v_room->>'clearedFrame')::bigint,
        v_clear_dur,
        (v_room->>'cleared')::boolean
      ) returning id into v_room_id;

      -- mémoriser roomIndex -> Room.id pour relier les player states
      v_room_map := v_room_map || jsonb_build_object(v_room->>'roomIndex', v_room_id);

      -- Ennemis
      for v_enemy in select * from jsonb_array_elements(coalesce(v_room->'enemies', '[]'::jsonb))
      loop
        insert into public."Monster"("Type", "Variant")
        values ((v_enemy->>'type')::real, (v_enemy->>'variant')::bigint)
        on conflict ("Type", "Variant") do nothing;
        select id into v_monster_id from public."Monster"
          where "Type" = (v_enemy->>'type')::real and "Variant" = (v_enemy->>'variant')::bigint;

        insert into public."RoomMonster"(id_Room, id_Monster, "SubType", "Hp", "MaxHp")
        values (
          v_room_id, v_monster_id,
          (v_enemy->>'subType')::bigint,
          (v_enemy->>'hp')::real,
          (v_enemy->>'maxHp')::real
        );
      end loop;

      -- Boss
      for v_boss in select * from jsonb_array_elements(coalesce(v_room->'bosses', '[]'::jsonb))
      loop
        insert into public."Boss"("Type", "Variant", "Name")
        values (
          (v_boss->>'type')::bigint, (v_boss->>'variant')::bigint,
          'Boss_' || (v_boss->>'type') || '_' || (v_boss->>'variant')
        )
        on conflict ("Type", "Variant") do nothing;
        select id into v_boss_id from public."Boss"
          where "Type" = (v_boss->>'type')::bigint and "Variant" = (v_boss->>'variant')::bigint;

        insert into public."RoomBoss"(id_Room, id_Boss, "SubType")
        values (v_room_id, v_boss_id, (v_boss->>'subType')::bigint);
      end loop;
    end loop;

    -- Player states
    for v_ps in select * from jsonb_array_elements(coalesce(v_floor->'playerStates', '[]'::jsonb))
    loop
      insert into public."PlayerState"(
        id_Run, id_Stage, id_Room, "Frame",
        "Damage", "FireDelay", "ShotSpeed", "TearRange", "MoveSpeed", "Luck",
        "Hearts", "MaxHearts", "SoulHearts", "BlackHearts", "BoneHearts", "GoldenHearts",
        "Coins", "Bombs", "Keys"
      ) values (
        v_run_id, v_stage_id,
        nullif(v_room_map->>(v_ps->>'roomIndex'), '')::bigint,
        (v_ps->>'timestamp')::bigint,
        (v_ps->'stats'->>'damage')::real,
        (v_ps->'stats'->>'tears')::real,
        (v_ps->'stats'->>'shotSpeed')::real,
        (v_ps->'stats'->>'range')::real,
        (v_ps->'stats'->>'speed')::real,
        (v_ps->'stats'->>'luck')::real,
        (v_ps->'health'->>'hearts')::bigint,
        (v_ps->'health'->>'maxHearts')::bigint,
        (v_ps->'health'->>'soulHearts')::bigint,
        (v_ps->'health'->>'blackHearts')::bigint,
        (v_ps->'health'->>'boneHearts')::bigint,
        (v_ps->'health'->>'goldenHearts')::bigint,
        (v_ps->'consumables'->>'coins')::bigint,
        (v_ps->'consumables'->>'bombs')::bigint,
        (v_ps->'consumables'->>'keys')::bigint
      ) returning id into v_ps_id;

      -- Inventaire passif (avec Count)
      for v_item in select * from jsonb_array_elements(coalesce(v_ps->'items'->'passive', '[]'::jsonb))
      loop
        insert into public."PassiveItem"(id) values ((v_item->>'id')::bigint)
          on conflict (id) do nothing;
        insert into public."Inventory"(id_PlayerState, id_PassiveItem, "Count")
        values (v_ps_id, (v_item->>'id')::bigint, coalesce((v_item->>'count')::bigint, 1));
      end loop;

      -- Items actifs (multi-slot)
      v_idx := 0;
      for v_active in select * from jsonb_array_elements(coalesce(v_ps->'items'->'active', '[]'::jsonb))
      loop
        insert into public."ActiveItem"(id) values ((v_active->>'id')::bigint)
          on conflict (id) do nothing;
        insert into public."PlayerStateActive"(id_PlayerState, id_ActiveItem, "Charge", "Slot")
        values (v_ps_id, (v_active->>'id')::bigint, (v_active->>'charge')::bigint, v_idx);
        v_idx := v_idx + 1;
      end loop;

      -- Trinkets (multi-slot) — tableau d'ids
      v_idx := 0;
      for v_trinket in select * from jsonb_array_elements(coalesce(v_ps->'trinkets', '[]'::jsonb))
      loop
        insert into public."Trinket"(id) values ((v_trinket)::text::bigint)
          on conflict (id) do nothing;
        insert into public."PlayerStateTrinket"(id_PlayerState, id_Trinket, "Slot")
        values (v_ps_id, (v_trinket)::text::bigint, v_idx);
        v_idx := v_idx + 1;
      end loop;
    end loop;
  end loop;

  -- DamageTaken : delta de vie effective (Hearts+SoulHearts+BlackHearts) vs snapshot précédent
  with ordered as (
    select id,
           ("Hearts" + coalesce("SoulHearts",0) + coalesce("BlackHearts",0)) as eff,
           lag("Hearts" + coalesce("SoulHearts",0) + coalesce("BlackHearts",0))
             over (order by "Frame", id) as prev_eff
    from public."PlayerState"
    where id_Run = v_run_id
  )
  update public."PlayerState" ps
  set "DamageTaken" = greatest(0, ordered.prev_eff - ordered.eff)
  from ordered
  where ps.id = ordered.id and ordered.prev_eff is not null;

  return v_run_id;
end;
$$;

-- ============================================================================
-- 5. Sécurité — RLS insert-only via la fonction
-- ============================================================================
-- Verrouiller toutes les tables ; aucun accès direct pour anon/authenticated.
do $$
declare t text;
begin
  foreach t in array array[
    'User','PassiveItem','ActiveItem','Trinket','Monster','Boss','RawRun',
    'Run','Stage','Room','PlayerState','Inventory','PlayerStateActive',
    'PlayerStateTrinket','RoomMonster','RoomBoss'
  ]
  loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('revoke all on public.%I from anon, authenticated;', t);
  end loop;
end $$;

-- Seul point d'entrée pour la clé publique : la fonction import_run.
grant execute on function public.import_run(jsonb) to anon, authenticated;
