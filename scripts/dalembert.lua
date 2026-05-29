-- D'Alembert Strategy
-- Increase by 1 unit after loss, decrease by 1 after win

function dobet()
    if win then
        nextbet = math.max(basebet, previousbet - basebet)
    else
        nextbet = previousbet + basebet
    end
end
