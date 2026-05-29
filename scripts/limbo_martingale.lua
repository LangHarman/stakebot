--[[
  Limbo Martingale (Taraje-compatible)
  Double bet on loss for Limbo, reset on win.
  Uses mutual bet for target/multiplier.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

-- target in Limbo = multiplier target (not chance)
target = 2.0

function chance_to_target(chance_val)
    return tonumber(string.format("%.2f", (99 / chance_val)))
end

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
