-- One-time helper: dumps all item IDs + Quality to the debug log.
-- Call DumpQualities() from the console or hook it to a callback once.
-- Output is parsed by DataBase/update_quality.py

local function DumpQualities()
    local itemConfig = Isaac.GetItemConfig()
    local maxItem = itemConfig:GetCollectibles().Size - 1

    Isaac.DebugString("[QualityDump:START]")

    for i = 1, maxItem do
        local cfg = itemConfig:GetCollectible(i)
        if cfg then
            -- Tags: 0 = no special tag; we only care about quality here
            local itemType = cfg.Type  -- 1 = passive, 3 = active, 4 = familiar (counted as passive)
            Isaac.DebugString(string.format(
                "[QualityDump] id=%d quality=%d type=%d name=%s",
                i, cfg.Quality, itemType, cfg.Name or "?"
            ))
        end
    end

    Isaac.DebugString("[QualityDump:END]")
    print("Quality dump complete — check the debug log.")
end

return DumpQualities
