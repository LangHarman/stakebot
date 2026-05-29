-- Limbo Bully Strategy
-- After loss, increase multiplier (recovery mode)
-- After win streak, keep going

bully_mult = 1.01  -- default recovery multiplier
function dobet()
    if win then
        nextbet = basebet
    else
        -- small recovery bet at very low multiplier
        nextbet = previousbet * 1.5
    end
end
