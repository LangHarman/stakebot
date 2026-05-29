--[[
  Martingale Strategy (Taraje/Seuntjie DiceBot compatible)
  Double bet on loss, reset on win.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

chance = 49.5
bethigh = true

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
