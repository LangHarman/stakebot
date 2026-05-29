--[[
  Fibonacci Strategy (Taraje-compatible)
  Uses Fibonacci sequence for bet sizing.
  On loss: advance 1 step in sequence
  On win: retreat 2 steps
]]
basebet = 0.00000001
currency = "btc"
nextbet = basebet

chance = 49.5
bethigh = true

-- Fibonacci sequence
fib = {1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610}
fibIndex = 1

function dobet()
    if win then
        -- Retreat 2 steps
        fibIndex = fibIndex - 2
        if fibIndex < 1 then
            fibIndex = 1
        end
        nextbet = basebet * fib[fibIndex]
    else
        -- Advance 1 step
        fibIndex = fibIndex + 1
        if fibIndex > #fib then
            fibIndex = #fib
        end
        nextbet = basebet * fib[fibIndex]
    end
end
