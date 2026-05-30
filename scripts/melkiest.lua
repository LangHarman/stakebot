-- melkiest.lua — 3-Phase Strategy for Limbo
-- Wager → Recovery → Paus (rare random spawn)
-- Made by Melky & Batavian Jaker

script_controls_all = true  -- fully self-contained, CLI skips base bet + target

phase = 1             -- 1=wager, 2=recovery, 3=paus
phase_start_profit = 0
phase_pnl = 0
phase_bets = 0

function init()
    phase = 1
    phase_start_profit = 0
    phase_pnl = 0
    phase_bets = 0
    nextbet = 0.0001
    chance = 1.01
end

function switch_phase(new_phase)
    phase = new_phase
    phase_start_profit = profit
    phase_pnl = 0
    phase_bets = 0
end

function random_paus()
    -- ~20% chance to spawn Paus after Recovery
    return math.random() < 0.2
end

function dobet()
    -- First bet of this phase — init bet values only
    if phase_bets == 0 then
        phase_bets = 1
        if phase == 1 then
            nextbet = 0.0001
            chance = 1.01
        elseif phase == 2 then
            nextbet = 0.00005
            chance = 1.58 + math.random() * 0.86
        elseif phase == 3 then
            nextbet = 0.00001
            chance = 18 + math.random() * 6
        end
        return
    end

    phase_pnl = profit - phase_start_profit
    phase_bets = phase_bets + 1

    -- ── Set multiplier per phase ──
    if phase == 1 then
        chance = 1.01
    elseif phase == 2 then
        chance = 1.58 + math.random() * 0.86
    elseif phase == 3 then
        chance = 18 + math.random() * 6
    end

    -- ── Phase Logic ──
    if phase == 1 then
        -- WAGER: flat 0.0001 @ 1.01x, switch on loss -0.0005
        nextbet = 0.0001
        if phase_pnl <= -0.0005 then
            switch_phase(2)
        end

    elseif phase == 2 then
        -- RECOVERY: martingale 1.3x, random 1.58-2.44x, switch when phase_pnl >= 0.0005
        if win then
            nextbet = previousbet
        else
            nextbet = previousbet * 1.3
        end
        if phase_pnl >= 0.0005 then
            if random_paus() then
                switch_phase(3)
            else
                switch_phase(1)
            end
        end

    elseif phase == 3 then
        -- PAUS: tiny bet 0.00001, multiplier 18-24x, martingale 1.02x
        if win then
            nextbet = previousbet
        else
            nextbet = previousbet * 1.02
        end
        if phase_pnl >= 0.0005 then
            switch_phase(1)
        end
    end
end
