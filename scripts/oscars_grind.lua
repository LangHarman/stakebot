--[[
  Oscar's Grind (Taraje-compatible)
  After a win, increase bet by 1 unit. After loss, keep same bet.
  Stop session when profit reaches 1 unit.
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

chance = 49.5
bethigh = true
targetProfit = basebet * 5

sessionUnits = 1
inSession = false

function dobet()
    if profit >= targetProfit then
        stop()
        return
    end

    if win then
        if not inSession then
            inSession = true
            sessionUnits = 1
        end
        sessionUnits = sessionUnits + 1
        nextbet = basebet * sessionUnits
    else
        -- On loss, keep same bet (Oscar's Grind rule)
        if not inSession then
            nextbet = basebet
        else
            nextbet = basebet * sessionUnits
        end
    end
end
