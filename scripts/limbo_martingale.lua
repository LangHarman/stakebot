-- Limbo Martingale
-- Double bet on loss (classic martingale for high-multiplier limbo)

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
