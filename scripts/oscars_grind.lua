-- Oscar's Grind
-- Increase bet by 1 unit after each win in a losing session
-- Reset after reaching +1 unit profit
-- Goal: grind small consistent profits
basebet = 0.000001
unit = 0.000001
bethigh = true
chance = 49.5
currentbet = basebet

function dobet()
    if win then
        if profit >= 0 then
            -- We're profitable, reset
            nextbet = basebet
        else
            -- Still in recovery: increase bet
            currentbet = currentbet + unit
            if currentbet > basebet * 10 then
                currentbet = basebet
            end
            nextbet = currentbet
        end
    else
        -- On loss: keep current bet
        nextbet = currentbet
    end
end
