-- SC Mining — adapted for GambaBot Limbo
-- Original: "SC Mining By Google" (Stake.com script)
-- State machine: first → second → third
-- Aims for 2 consecutive wins; martingale on miss
-- Adapted by Melky, May 30 2026

-- ═══ Settings ═══
mina = 52.95              -- min win chance %
maxa = 62.95              -- max win chance %
seed_reset_interval = 500 -- reseed every N bets
profittarget = 999.0      -- session profit target

-- ═══ State Machine ═══
first = true
second = false
secondwin = false
third = false
betcount = 100            -- near interval to force early reseed

-- ═══ Init — runs after CLI values are injected ═══
function init()
    base = basebet
    nextbet = base
    local pct = math.random(mina * 100, maxa * 100) / 100
    chance = tonumber(string.format("%.2f", 99 / pct))
    first = true
    second = false
    secondwin = false
    third = false
    betcount = 100
end

-- ═══ Main Bet Logic ═══
function dobet()
    -- Seed rotation
    betcount = betcount + 1
    if betcount >= seed_reset_interval then
        betcount = 0
        resetseed()
    end

    -- Global stop checks
    -- Note: balance < nextbet is handled by engine (GambaBot starts balance at 0)
    if balance > 0 and balance >= profittarget then
        stop()
        return
    end

    local done = false

    if win then
        -- ═══ WIN PATH ═══
        if first then
            -- Stay in first, pick new random target
            local pct = math.random(mina * 100, maxa * 100) / 100
            chance = tonumber(string.format("%.2f", 99 / pct))
            nextbet = base
        end

        if second then
            secondwin = true
            second = false
            third = true
            done = true
        end

        if third and not done then
            if secondwin then
                nextbet = base          -- ✅ WW: reset
            else
                nextbet = previousbet * 3  -- WL: martingale 3x
            end
            third = false
            first = true
        end

    else
        -- ═══ LOSS PATH ═══
        if first and not done then
            first = false
            second = true
            done = true
        end

        if second and not done then
            secondwin = false
            second = false
            third = true
            done = true
        end

        if third and not done then
            third = false
            first = true
            if secondwin then
                nextbet = previousbet * 3    -- LW: martingale 3x
            else
                nextbet = previousbet * 4.5  -- LL: martingale 4.5x
            end
        end
    end
end
