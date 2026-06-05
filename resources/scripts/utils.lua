local Utils = {}

function Utils.randomRange(min, max)
    return math.random(min, max)
end

function Utils.clamp(value, min, max)
    return math.max(min, math.min(max, value))
end

function Utils.round(value)
    return math.floor(value + 0.5)
end

return Utils