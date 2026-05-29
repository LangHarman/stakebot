--[[
  D'Alembert Strategy (Taraje-compatible)
  Up 1 unit on loss, down 1 unit on win.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

chance = 49.5
bethigh = true

function dobet()
    if win then
        nextbet = previousbet - basebet
        if nextbet < basebet then
            nextbet = basebet
        end
    else
        nextbet = previousbet + basebet
    end
end
