--[[
  Reverse Martingale (Taraje-compatible)
  Double bet on win, reset on loss.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

chance = 49.5
bethigh = true

function dobet()
    if win then
        nextbet = previousbet * 2
    else
        nextbet = basebet
    end
end
