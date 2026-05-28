"""
LUA Script mode - compatible with Seuntjie DiceBot Programmer Mode.
Run custom LUA strategies that control bet size, chance, and direction.
"""
import sys
import os
import math
import asyncio
from typing import Optional, Any
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from lupa import LuaRuntime
    HAS_LUA = True
except ImportError:
    HAS_LUA = False

from core.client import StakeClient, StakeConfig
from core.engine import BettingEngine, StopConditions, BetStats


def _lua_get(lua_table, key, default=None):
    """Safely get a value from a Lua globals table (no .get() method)."""
    try:
        val = lua_table[key]
        if val is None:
            return default
        return val
    except (KeyError, TypeError):
        return default


@dataclass
class ScriptGlobals:
    """Available variables/functions exposed to LUA scripts."""
    # Read-Only (set by engine)
    balance: float = 0.0
    profit: float = 0.0
    wins: int = 0
    losses: int = 0
    total_bets: int = 0
    current_streak: int = 0

    # Read-Write (script can modify these)
    nextbet: float = 0.000001
    chance: float = 49.5
    high: bool = True
    game_type: str = "dice"  # "dice" or "limbo"

    # Last bet result
    lastBet: dict = field(default_factory=lambda: {
        "id": "",
        "amount": 0.0,
        "payout": 0.0,
        "multiplier": 0.0,
        "outcome": "",
        "won": False,
        # Limbo-specific
        "crash_point": 0.0,
        "target_multiplier": 0.0,
    })


class LuaScriptEngine:
    """
    Lua script executor compatible with Seuntjie DiceBot.

    Exposes to Lua:
    - Variables: balance, profit, wins, losses, nextbet, chance, high, lastBet
    - Functions: print(), stop(), debug()
    - dobet() must be defined in user script
    """

    def __init__(self):
        if not HAS_LUA:
            raise ImportError("lupa not installed. Run: pip install lupa")

        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self._py_globals = ScriptGlobals()
        self._stop_requested = False
        self.engine: Optional[BettingEngine] = None
        self._register_functions()

    def _register_functions(self):
        """Register helper functions accessible from Lua."""
        lua = self.lua
        g = lua.globals()

        # print() - Lua print
        def lua_print(*args):
            msg = " ".join(str(a) for a in args)
            sys.stdout.write(f"[LUA] {msg}\n")
            sys.stdout.flush()
        g['print'] = lua_print

        # stop() - request stop
        def stop():
            self._stop_requested = True
            raise StopIteration("Script requested stop")
        g['stop'] = stop

        # debug() - print debug info
        def debug(*args):
            msg = " ".join(str(a) for a in args)
            sys.stdout.write(f"[DEBUG] {msg}\n")
            sys.stdout.flush()
        g['debug'] = debug

        # win convenience variable (gets set before dobet call)
        g['win'] = False
        g['previousbet'] = 0.000001

    def _sync_globals_to_lua(self):
        """Copy Python globals to Lua environment."""
        g = self._py_globals
        lg = self.lua.globals()

        lg['balance'] = g.balance
        lg['profit'] = g.profit
        lg['wins'] = g.wins
        lg['losses'] = g.losses
        lg['total_bets'] = g.total_bets
        lg['current_streak'] = g.current_streak
        lg['nextbet'] = g.nextbet
        lg['chance'] = g.chance
        lg['high'] = g.high

        # lastBet as Lua table
        lb = g.lastBet
        lg['lastBet'] = {
            'id': lb.get('id', ''),
            'amount': lb.get('amount', 0.0),
            'payout': lb.get('payout', 0.0),
            'multiplier': lb.get('multiplier', 0.0),
            'outcome': lb.get('outcome', ''),
            'won': lb.get('won', False),
            'WON': lb.get('won', False),
            'crash_point': lb.get('crash_point', 0.0),
            'target_multiplier': lb.get('target_multiplier', 0.0),
        }

        # Convenience aliases
        lg['win'] = lb.get('won', False)
        lg['previousbet'] = lb.get('amount', 0.0)
        lg['crash'] = lb.get('crash_point', 0.0)  # Short alias for limbo

    def _sync_lua_to_globals(self):
        """Read modified Lua variables back to Python."""
        lg = self.lua.globals()
        g = self._py_globals

        g.nextbet = float(_lua_get(lg, 'nextbet', g.nextbet))
        g.chance = float(_lua_get(lg, 'chance', g.chance))
        high_val = _lua_get(lg, 'high', g.high)
        if isinstance(high_val, bool):
            g.high = high_val
        elif isinstance(high_val, (int, float)):
            g.high = high_val != 0

    def load_script(self, script_code: str):
        """Load and parse a Lua script."""
        lg = self.lua.globals()
        self.lua.execute(script_code)

        # Verify dobet() exists
        dobet = _lua_get(lg, 'dobet')
        if dobet is None:
            raise ValueError(
                "Script must define a 'dobet()' function!\n\n"
                "Example:\n"
                "  basebet = 0.000001\n"
                "  chance = 49.5\n"
                "  bethigh = true\n"
                "\n"
                "  function dobet()\n"
                "    if win then\n"
                "      nextbet = basebet\n"
                "    else\n"
                "      nextbet = previousbet * 2\n"
                "    end\n"
                "  end"
            )

        # Detect game type: limbo if target_multiplier is set at top-level
        tm_val = _lua_get(lg, 'target_multiplier')
        if tm_val and float(tm_val) >= 1.01:
            self._py_globals.game_type = "limbo"
            self._py_globals.lastBet["target_multiplier"] = float(tm_val)

        # Respect chance/bethigh set by script at top-level
        chance_val = _lua_get(lg, 'chance')
        if chance_val:
            self._py_globals.chance = float(chance_val)

        bethigh_val = _lua_get(lg, 'bethigh')
        if bethigh_val is not None:
            self._py_globals.high = bool(bethigh_val)

        basebet_val = _lua_get(lg, 'basebet')
        if basebet_val:
            self._py_globals.nextbet = float(basebet_val)

    def call_dobet(self):
        """Execute dobet() in Lua. Called after each bet result."""
        if self._stop_requested:
            raise StopIteration("Stop requested")

        lg = self.lua.globals()
        dobet = _lua_get(lg, 'dobet')
        if dobet:
            # Sync current state to Lua
            self._sync_globals_to_lua()

            # Call dobet()
            dobet()

            # Read back modified vars
            self._sync_lua_to_globals()

    def update_state(self, stats: BetStats, last_bet: dict):
        """Update engine state before calling dobet()."""
        g = self._py_globals
        g.balance = stats.current_balance
        g.profit = stats.net_profit
        g.wins = stats.wins
        g.losses = stats.losses
        g.total_bets = stats.total_bets
        g.current_streak = stats.current_streak
        g.lastBet = last_bet

    def get_bet_params(self) -> dict:
        """Get current bet parameters (after script's dobet() ran)."""
        game_type = self._py_globals.game_type
        chance = self._py_globals.chance

        if game_type == "limbo":
            # Use target_multiplier from lastBet if set, else derive from chance
            tm = self._py_globals.lastBet.get("target_multiplier", 0)
            if tm < 1.01 and chance > 0:
                # Stake limbo: payout = (99 / chance) * 0.99
                tm = round((99.0 / chance) * 0.99, 4)
            if tm < 1.01:
                tm = 2.0
            return {
                "amount": round(self._py_globals.nextbet, 8),
                "target_multiplier": tm,
                "game_type": "limbo",
            }
        else:
            if chance <= 0 or chance >= 100:
                chance = 49.5
            if self._py_globals.high:
                target = round(100 - (chance * 100 / 100), 2)
            else:
                target = round(chance * 100 / 100, 2)
            return {
                "amount": round(self._py_globals.nextbet, 8),
                "target": target,
                "over": self._py_globals.high,
                "chance": chance,
                "game_type": "dice",
            }

    def reset(self):
        """Reset script state."""
        self._py_globals = ScriptGlobals()
        self._stop_requested = False


def get_script_path(name: str) -> str:
    """Resolve script file path."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    scripts_dir = os.path.join(base_dir, "scripts")

    if os.path.exists(name):
        return name
    path = os.path.join(scripts_dir, name)
    if os.path.exists(path):
        return path
    if not name.endswith(".lua"):
        path = os.path.join(scripts_dir, name + ".lua")
        if os.path.exists(path):
            return path
    return name


async def run_script(cfg, script_path: str, max_bets: int = 0):
    """Run LUA script betting mode."""
    if not HAS_LUA:
        print("❌ lupa library required. Install: pip install lupa")
        return

    script_path = get_script_path(script_path)
    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return

    script_code = open(script_path).read()
    print(f"\n📜 Loaded script: {script_path}")
    print("   Lines:", len(script_code.splitlines()))
    print("─" * 50)

    async with StakeClient(cfg) as client:
        print("🔄 Testing authentication...")
        ok = await client.check_auth()
        if not ok:
            print("❌ Authentication failed!")
            return
        print("✅ Authentication OK!")

        try:
            lua_engine = LuaScriptEngine()
            lua_engine.load_script(script_code)
            print("✅ Lua script loaded successfully")
        except Exception as e:
            print(f"❌ Lua script error: {e}")
            return

        # Detect game type from script
        game_type = lua_engine._py_globals.game_type
        game_icon = "🚀 Limbo" if game_type == "limbo" else "🎲 Dice"
        print(f"  Game: {game_icon}")

        print("\n" + "─" * 55)
        print("  📋 Script Mode — Press Enter to start (Ctrl+C to stop)")
        print("─" * 55)
        input()

        # Build game-specific place_bet function
        if game_type == "limbo":
            async def bet_fn(amount, target_multiplier=None, **kw):
                return await client.place_limbo_bet(
                    amount=amount, target_multiplier=target_multiplier
                )
        else:
            async def bet_fn(amount, target=None, over=None, **kw):
                return await client.place_dice_bet(
                    amount=amount, target=target, over=over
                )

        engine = BettingEngine(
            place_bet_fn=bet_fn,
            get_balance_fn=lambda: client.get_balance_simple(),
        )
        engine.config.game_type = game_type

        # Track last bet info for script
        _last_was_win = [False]
        _last_amount = [0.0]
        _last_crash = [0.0]
        _last_tm = [0.0]

        def strategy_callback(stats):
            lua_engine.update_state(stats, {
                "amount": _last_amount[0],
                "won": _last_was_win[0],
                "multiplier": 0.0,
                "crash_point": _last_crash[0],
                "target_multiplier": _last_tm[0],
            })
            lua_engine.call_dobet()
            return lua_engine.get_bet_params()

        engine.set_strategy(strategy_callback)

        # Patch engine to track bet results for script
        original_place = engine.place_bet

        async def tracked_place(*args, **kwargs):
            result = await original_place(*args, **kwargs)
            _last_was_win[0] = result.get("won", False)
            _last_amount[0] = result.get("amount", kwargs.get("amount", 0))
            _last_crash[0] = result.get("crash_point", 0)
            _last_tm[0] = result.get("target_multiplier", 0)
            return result

        engine.place_bet = tracked_place

        if max_bets > 0:
            engine.stop_conditions.max_bets = max_bets

        await engine.run()


# ── Example Lua Scripts ─────────────────────────────────

EXAMPLE_SCRIPTS = {
    "martingale": """
-- Martingale Strategy
-- Double bet on loss, reset on win
basebet = 0.000001
bethigh = true
chance = 49.5

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
""",

    "reverse_martingale": """
-- Reverse Martingale (Paroli)
-- Double bet on win, reset on loss
basebet = 0.000001
bethigh = true
chance = 49.5

function dobet()
    if win then
        nextbet = previousbet * 2
    else
        nextbet = basebet
    end
end
""",

    "dalembert": """
-- D'Alembert Strategy
-- Increase bet by 1 unit on loss, decrease by 1 unit on win
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
""",

    "oscars_grind": """
-- Oscar's Grind
-- Increase bet by 1 unit after a win, reset after reaching +1 unit profit
basebet = 0.000001
unit = 0.000001
bethigh = true
chance = 49.5
currentbet = basebet

function dobet()
    if win then
        if profit >= 0 then
            nextbet = basebet
        else
            currentbet = currentbet + unit
            if currentbet > basebet * 10 then
                currentbet = basebet
            end
            nextbet = currentbet
        end
    else
        nextbet = currentbet
    end
end
""",

    "limbo": """
-- Limbo Strategy Template
-- Set target_multiplier at top level to auto-enable Limbo mode
-- Available extra vars: crash (last crash point), lastBet.crash_point

target_multiplier = 2.0
basebet = 0.000001
chance = 49.5

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end

    print("Crash: " .. crash .. "x")
end
""",

    "custom": """
-- Custom Strategy Template (Dice or Limbo)
-- Available variables:
--   balance, profit, wins, losses, total_bets, current_streak
--   win, previousbet, crash (limbo only)
--   lastBet: amount, payout, multiplier, won, crash_point, target_multiplier
-- RW: nextbet, chance, high
--
-- Untuk Limbo: set target_multiplier di top-level

basebet = 0.000001
bethigh = true
chance = 49.5
nextbet = basebet

function dobet()
    -- ← Write your strategy here!

    -- Example: simple martingale
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end

    -- Stop if we've lost too much
    if profit < -0.01 then
        stop()
    end
end
""",
}
