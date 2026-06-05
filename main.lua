StageAnalyser = RegisterMod("StageAnalyser", 1)
local mod = StageAnalyser
local game = Game()

-- Charger le module de collecte de données
local DataCollector = require("resources.scripts.data_collector")
local DumpQualities = require("resources.scripts.dump_qualities")

local _qualityDumped = false

function mod:OnInit()
    Isaac.DebugString("StageAnalyser initialized")
end

-- Callback pour nouvelle partie
function mod:OnGameStart(isContinued)
    -- One-time quality dump on the very first game start
    if not _qualityDumped then
        DumpQualities()
        _qualityDumped = true
    end

    if not isContinued then
        -- Nouvelle run
        DataCollector:InitRun()
    end
    DataCollector:InitFloor()
    DataCollector:SavePlayerState()
end

-- Callback pour changement de stage
function mod:OnNewLevel()
    DataCollector:InitFloor()
    DataCollector:SavePlayerState()
end

-- Callback pour changement de room
function mod:OnNewRoom()
    DataCollector:RecordRoom()
    DataCollector:SavePlayerState()
end

-- Callback pour room cleared
function mod:OnRoomClear()
    Isaac.DebugString("[StageAnalyser] Room cleared")
    DataCollector:OnRoomCleared()
    DataCollector:SavePlayerState()
end

-- Callback pour victoire
-- isGameOver is true on death/loss, false on win
function mod:OnGameEnd(isGameOver)
    Isaac.DebugString("[StageAnalyser] Game ended")
    DataCollector:EndRun(not isGameOver)
end

mod:AddCallback(ModCallbacks.MC_POST_GAME_STARTED, mod.OnGameStart)
mod:AddCallback(ModCallbacks.MC_POST_NEW_LEVEL, mod.OnNewLevel)
mod:AddCallback(ModCallbacks.MC_POST_NEW_ROOM, mod.OnNewRoom)
mod:AddCallback(ModCallbacks.MC_PRE_SPAWN_CLEAN_AWARD, mod.OnRoomClear)
mod:AddCallback(ModCallbacks.MC_POST_GAME_END, mod.OnGameEnd)