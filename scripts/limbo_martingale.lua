-- Limbo Martingale
-- Target multiplier: 2x, double on loss, reset on win
-- Untuk game Limbo di Stake.com

target_multiplier = 2
basebet = 0.000001
chance = 49.5  -- Payout ~2x for Limbo

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end

    -- Optional: adjust target based on streak
    if current_streak < -5 then
        -- After 5 losses, lower target
        target_multiplier = 1.5
    elseif current_streak == 0 then
        target_multiplier = 2
    end
end
