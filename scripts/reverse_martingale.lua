-- Reverse Martingale Strategy
-- Double bet after win, reset after loss

function dobet()
    if win then
        nextbet = previousbet * 2
    else
        nextbet = basebet
    end
end
