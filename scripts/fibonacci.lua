-- Fibonacci Strategy
-- Use Fibonacci sequence: bet[n] = bet[n-1] + bet[n-2] after loss
-- Step back 2 positions after win

fib = {1, 1}
fib_pos = 0

function dobet()
    if fib_pos == 0 then
        fib_pos = 1
    end

    if fib_pos > #fib then
        fib[fib_pos] = fib[fib_pos-1] + fib[fib_pos-2]
    end

    nextbet = basebet * fib[fib_pos]

    if win then
        fib_pos = math.max(0, fib_pos - 2)
    else
        fib_pos = fib_pos + 1
    end
end
