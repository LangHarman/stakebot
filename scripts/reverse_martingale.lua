-- Reverse Martingale (Paroli)
-- Double bet on win, reset to base on loss
-- Ride winning streaks, minimize losses
basebet = 0.000001
bethigh = true
chance = 49.5

function dobet()
    if win then
        nextbet = previousbet * 2
    else
        nextbet = basebet
    end
end
