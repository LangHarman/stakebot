-- Limbo Bully Strategy
-- Target multiplier rendah (1.1x - 1.5x) untuk win rate tinggi
-- Increase bet gradually on loss, reset on win

target_multiplier = 1.2
basebet = 0.000001
chance = 80.0  -- ~80% chance to win at 1.2x

function dobet()
    if win then
        nextbet = basebet
    else
        -- Increase by 50% on loss
        nextbet = previousbet * 1.5
    end

    -- Safety: don't let bet get too big
    if nextbet > basebet * 100 then
        stop()
    end

    print("Balance: " .. balance .. " | Crash: " .. crash)
end
