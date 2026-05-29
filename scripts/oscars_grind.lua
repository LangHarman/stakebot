-- Oscar's Grind Strategy
-- Increment by 1 unit after win (until profit), never change after loss

oscars_next = 0

function dobet()
    if oscars_next == 0 then
        oscars_next = basebet
    end

    nextbet = oscars_next

    if win then
        if profit + nextbet > 0 then
            oscars_next = basebet
        else
            oscars_next = math.min(basebet + nextbet, basebet * 10)
        end
    end
end
