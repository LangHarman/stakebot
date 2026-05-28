-- D'Alembert Strategy
-- Increase bet by 1 unit on loss, decrease by 1 unit on win
-- More conservative than martingale
basebet = 0.000001
unit = 0.000001
bethigh = false
chance = 50

function dobet()
    if win then
        nextbet = previousbet - unit
        if nextbet < basebet then
            nextbet = basebet
        end
    else
        nextbet = previousbet + unit
    end
end
