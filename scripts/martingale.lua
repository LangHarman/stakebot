-- Martingale Strategy
-- Double bet after loss, reset after win
-- Variables available: basebet, nextbet, chance, bethigh, balance, profit, currentstreak

function dobet()
    if win then
        nextbet = basebet
        isFirstGreen = true
    else
        nextbet = previousbet * 2
        isFirstRed = true
    end
end
