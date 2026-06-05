local mod = RegisterMod("My Isaac Mod", 1)

function mod:onPlayerInit(player)
    -- Code to execute when a player is initialized
end

function mod:onGameStart()
    -- Code to execute when the game starts
end

function mod:onUpdate()
    -- Code to execute on each game update
end

mod:AddCallback(ModCallbacks.MC_POST_PLAYER_INIT, mod.onPlayerInit)
mod:AddCallback(ModCallbacks.MC_POST_GAME_STARTED, mod.onGameStart)
mod:AddCallback(ModCallbacks.MC_POST_UPDATE, mod.onUpdate)