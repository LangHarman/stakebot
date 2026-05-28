-- Martingale Strategy
-- Double bet on loss, reset to base on win
-- Classic "never lose" strategy (until you hit table limit)
basebet = 0.000001
bethigh = true
chance = 49.5

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
