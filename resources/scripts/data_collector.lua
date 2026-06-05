local DataCollector = {}

-- Structure pour stocker toutes les données de la run
DataCollector.runData = {
	runID = nil,
	seed = "",
	startTime = 0,
	character = "",
	floors = {},
	currentFloor = nil,
	isActive = false,
}

-- Initialiser une nouvelle run
function DataCollector:InitRun()
	local game = Game()
	local player = game:GetPlayer(0)
	local seeds = game:GetSeeds()

	local timestamp = Isaac.GetFrameCount()
	self.runData = {
		runID = timestamp,
		seed = seeds:GetStartSeedString(),
		startTime = timestamp,
		character = player:GetPlayerType(),
		floors = {},
		currentFloor = nil,
		isActive = true,
	}

	Isaac.DebugString("[DataCollector] New run initialized: " .. self.runData.seed)
	return self.runData
end

-- Initialiser un nouveau floor
function DataCollector:InitFloor()
	local game = Game()
	local level = game:GetLevel()

	local floorData = {
		floorID = Isaac.GetFrameCount(),
		stageNumber = level:GetStage(),
		stageType = level:GetStageType(),
		stageName = self:GetStageName(level:GetStage(), level:GetStageType()),
		rooms = {},
		playerStates = {},
	}

	table.insert(self.runData.floors, floorData)
	self.runData.currentFloor = floorData

	Isaac.DebugString("[DataCollector] New floor: " .. floorData.stageName)
	return floorData
end

-- Récupérer les items du joueur
function DataCollector:GetPlayerItems(player)
	local items = {
		passive = {},
		active = {},
	}

	-- Items passifs (on parcourt tous les items possibles)
	local maxItem = Isaac.GetItemConfig():GetCollectibles().Size - 1
	for i = 1, maxItem do
		if player:HasCollectible(i) then
			table.insert(items.passive, {
				id = i,
				count = player:GetCollectibleNum(i),
			})
		end
	end

	-- Item actif
	local activeItem = player:GetActiveItem()
	if activeItem > 0 then
		table.insert(items.active, {
			id = activeItem,
			charge = player:GetActiveCharge(),
		})
	end

	return items
end

-- Récupérer les trinkets
function DataCollector:GetPlayerTrinkets(player)
	local trinkets = {}

	-- Trinket slot 1
	local trinket1 = player:GetTrinket(0)
	if trinket1 > 0 then
		table.insert(trinkets, trinket1)
	end

	-- Trinket slot 2
	local trinket2 = player:GetTrinket(1)
	if trinket2 > 0 then
		table.insert(trinkets, trinket2)
	end

	return trinkets
end

-- Sauvegarder l'état du joueur
function DataCollector:SavePlayerState()
	if not self.runData.isActive or not self.runData.currentFloor then
		return
	end

	local game = Game()
	local player = game:GetPlayer(0)
	local level = game:GetLevel()

	local playerState = {
		timestamp = Isaac.GetFrameCount(),
		roomIndex = level:GetCurrentRoomIndex(),
		-- Stats du joueur
		health = {
			hearts = player:GetHearts(),
			maxHearts = player:GetMaxHearts(),
			soulHearts = player:GetSoulHearts(),
			blackHearts = player:GetBlackHearts(),
			boneHearts = player:GetBoneHearts(),
			goldenHearts = player:GetGoldenHearts(),
		},
		-- Stats
		stats = {
			damage = player.Damage,
			tears = player.MaxFireDelay,
			speed = player.MoveSpeed,
			range = player.TearRange,
			shotSpeed = player.ShotSpeed,
			luck = player.Luck,
		},
		-- Items
		items = self:GetPlayerItems(player),
		trinkets = self:GetPlayerTrinkets(player),
		-- Consumables
		consumables = {
			coins = player:GetNumCoins(),
			bombs = player:GetNumBombs(),
			keys = player:GetNumKeys(),
		},
	}

	table.insert(self.runData.currentFloor.playerStates, playerState)
	return playerState
end

-- Enregistrer une room
function DataCollector:RecordRoom()
	if not self.runData.isActive or not self.runData.currentFloor then
		return
	end

	local game = Game()
	local level = game:GetLevel()
	local room = game:GetRoom()

	local roomIndex = level:GetCurrentRoomIndex()

	-- Vérifier si la room existe déjà
	for _, r in ipairs(self.runData.currentFloor.rooms) do
		if r.roomIndex == roomIndex then
			-- Room déjà visitée
			return r
		end
	end

	local roomType = room:GetType()

	-- Nouvelle room
	local roomData = {
		roomIndex = roomIndex,
		roomType = roomType,
		roomTypeName = self:GetRoomTypeName(roomType),
		visited = true,
		cleared = room:IsClear(),
		enemies = self:GetRoomEnemies(),
		bosses = self:GetRoomBosses(roomType),
		enterFrame = Isaac.GetFrameCount(),
		clearedFrame = nil,
		timestamp = Isaac.GetFrameCount(),
	}

	table.insert(self.runData.currentFloor.rooms, roomData)
	Isaac.DebugString("[DataCollector] Room recorded: " .. roomData.roomTypeName)

	return roomData
end

-- Récupérer les ennemis dans la room
function DataCollector:GetRoomEnemies()
	local enemies = {}
	local entities = Isaac.GetRoomEntities()

	for i = 1, #entities do
		local entity = entities[i]
		if entity:IsEnemy() and entity:IsVulnerableEnemy() then
			table.insert(enemies, {
				type = entity.Type,
				variant = entity.Variant,
				subType = entity.SubType,
				hp = entity.HitPoints,
				maxHp = entity.MaxHitPoints,
			})
		end
	end

	return enemies
end

-- Récupérer les boss dans la room (uniquement pour les Boss rooms, type 5)
function DataCollector:GetRoomBosses(roomType)
	if roomType ~= 5 then
		return {}
	end

	local bosses = {}
	local entities = Isaac.GetRoomEntities()

	for i = 1, #entities do
		local entity = entities[i]
		if entity:IsEnemy() and entity:IsBoss() then
			table.insert(bosses, {
				type = entity.Type,
				variant = entity.Variant,
				subType = entity.SubType,
			})
		end
	end

	return bosses
end

-- Marquer la room courante comme terminée
function DataCollector:OnRoomCleared()
	if not self.runData.isActive or not self.runData.currentFloor then
		return
	end

	local level = Game():GetLevel()
	local roomIndex = level:GetCurrentRoomIndex()

	for _, r in ipairs(self.runData.currentFloor.rooms) do
		if r.roomIndex == roomIndex then
			r.clearedFrame = Isaac.GetFrameCount()
			r.cleared = true
			return
		end
	end
end

-- Obtenir le nom du stage
function DataCollector:GetStageName(stage, stageType)
	-- stageType: 0=normal, 1=alt1, 2=alt2, 3=Repentance alt-path A, 4=Repentance alt-path B
	local stages = {
		[1] = { "Basement", "Cellar", "Burning Basement", nil, "Downpour", "Dross" },
		[2] = { "Caves", "Catacombs", "Flooded Caves", nil, "Mines", "Ashpit" },
		[3] = { "Depths", "Necropolis", "Dank Depths", nil, "Mausoleum", "Gehenna" },
		[4] = { "Womb", "Utero", "Scarred Womb", nil, "Corpse" },
		[5] = { "Sheol", "Cathedral" },
		[6] = { "Dark Room", "Chest" },
		[7] = { "The Void" },
		[8] = { "Home" },
	}

	if stages[stage] then
		local typeIndex = stageType + 1
		if stages[stage][typeIndex] then
			return stages[stage][typeIndex]
		end
		return stages[stage][1]
	end

	return "Unknown Stage"
end

-- Obtenir le nom du type de room
function DataCollector:GetRoomTypeName(roomType)
	local roomTypes = {
		[0] = "Default",
		[1] = "Normal",
		[2] = "Shop",
		[3] = "Error Room",
		[4] = "Treasure Room",
		[5] = "Boss",
		[6] = "Mini-Boss",
		[7] = "Secret Room",
		[8] = "Super Secret Room",
		[9] = "Arcade",
		[10] = "Curse Room",
		[11] = "Challenge Room",
		[12] = "Library",
		[13] = "Sacrifice Room",
		[14] = "Devil Room",
		[15] = "Angel Room",
		[16] = "Crawl Space",
		[17] = "Boss Rush",
		[18] = "Clean Bedroom",
		[19] = "Dirty Bedroom",
		[20] = "Vault",
		[21] = "Dice Room",
		[22] = "Black Market",
		[23] = "Greed Exit",
		[24] = "Planetarium",
		[25] = "Teleporter Entrance",
		[26] = "Teleporter Exit",
		[27] = "Ultra Secret Room",
	}

	return roomTypes[roomType] or "Unknown Room"
end

-- Terminer la run
function DataCollector:EndRun(victory)
	if not self.runData.isActive then
		return
	end

	self.runData.isActive = false
	self.runData.endTime = Isaac.GetFrameCount()
	self.runData.victory = victory or false
	self.runData.duration = self.runData.endTime - self.runData.startTime

	Isaac.DebugString("[DataCollector] Run ended. Duration: " .. self.runData.duration .. "s")

	-- Sauvegarder dans un fichier
	self:SaveToFile()

	return self.runData
end

-- Sauvegarder les données dans un fichier JSON
function DataCollector:SaveToFile()
	local json = require("json")
	local filename = "stageanalyser_" .. self.runData.runID .. ".json"

	Isaac.DebugString("[DataCollector] Saving run data to: " .. filename)

	-- Remove currentFloor reference before encoding to avoid duplicating the last floor
	self.runData.currentFloor = nil

	-- Convertir en JSON
	local jsonData = json.encode(self.runData)

	-- Note: Isaac ne permet pas d'écrire directement dans des fichiers
	-- Il faut utiliser Isaac.SaveModData ou exporter via la console debug
	Isaac.SaveModData(StageAnalyser, jsonData)

	-- Balises pour extraction via le log (push_from_log.py)
	Isaac.DebugString("[StageAnalyserJSON]" .. jsonData .. "[/StageAnalyserJSON]")
	Isaac.DebugString("[DataCollector] JSON Data logged for external export")
end

return DataCollector
