--[[
  Limbo Bully Strategy (Taraje-compatible)
  Aggressive Limbo: bet high multiplier, skip until first loss then bully.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

-- High multiplier target
target = 10.0

-- Bully level (increase after loss)
bullyLevel = 1

function dobet()
    if win then
        -- Reset on win
        nextbet = basebet
        bullyLevel = 1
    else
        -- Bully up on loss
        bullyLevel = bullyLevel + 1
        nextbet = basebet * bullyLevel
    end

    -- Increase target multiplier if we're bullying
    if bullyLevel > 1 then
        target = 5.0  -- Lower target = higher chance to win
    else
        target = 10.0 -- Normal target = lower chance, higher payout
    end
end
