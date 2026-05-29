"""
LUA scripting engine for StakeBot.
Compatible with Taraje/Seuntjie DiceBot LUA variables.

Variables (RW = LUA can read/write):
  basebet, nextbet, currency, bethigh, maxbet,
  resetIfLose, resetIfProfit, resetIfLoseStreak, resetIfWinStreak,
  targetBalance, targetProfit, targetLose, chance, target

Variables (RO = LUA can only read):
  balance, bets, profit, wins, losses, currentstreak, win,
  previousbet, lastBet (table), broker, seedChanged,
  isFirstGreen, isFirstRed, isMaxBetReached,
  isResetWinStreakReached, isResetLoseStreakReached,
  isResetProfitReached, isResetLossReached, isBetInterrupted

Functions:
  dobet()   - called by LUA, executed by engine
  stop()    - kill the bot
  resetseed(seed) - rotate client seed
  round(num, precision)
"""
from lupa import LuaRuntime
from typing import Optional


# ── DiceBot-compatible LUA variables ──
LUA_RW_VARS = [
    "basebet", "nextbet", "currency", "bethigh", "maxbet",
    "chance", "target",
    "resetIfLose", "resetIfProfit", "resetIfLoseStreak", "resetIfWinStreak",
    "targetBalance", "targetProfit", "targetLose",
    "profit_target", "loss_target",
    "protect_profile", "replay",
]

LUA_RO_VARS = [
    "balance", "bets", "profit", "wins", "losses",
    "currentstreak", "win", "previousbet", "lastBet",
    "broker", "seedChanged",
    "isFirstGreen", "isFirstRed", "isMaxBetReached",
    "isResetWinStreakReached", "isResetLoseStreakReached",
    "isResetProfitReached", "isResetLossReached",
    "isBetInterrupted",
]


class LuaScriptEngine:
    """LUA scripting engine wrapping lupa."""

    def __init__(self, script: str):
        self.script = script
        self.lua = LuaRuntime(unpack_returned_tuples=True)

        # State dictionary
        self.s = {
            # RW defaults
            "basebet": 0.00000001,
            "nextbet": 0.00000001,
            "currency": "btc",
            "bethigh": False,
            "maxbet": 0.0,
            "chance": 49.5,
            "target": 2.0,
            "resetIfLose": 0.0,
            "resetIfProfit": 0.0,
            "resetIfLoseStreak": 0,
            "resetIfWinStreak": 0,
            "targetBalance": 0.0,
            "targetProfit": 0.0,
            "targetLose": 0.0,
            "profit_target": 0.0,
            "loss_target": 0.0,
            "protect_profile": False,
            "replay": False,
            # RO defaults
            "balance": 0.0,
            "bets": 0,
            "profit": 0.0,
            "wins": 0,
            "losses": 0,
            "currentstreak": 0,
            "win": False,
            "previousbet": 0.0,
            "lastBet": {},
            "broker": "stake",
            "seedChanged": False,
            "isFirstGreen": False,
            "isFirstRed": False,
            "isMaxBetReached": False,
            "isResetWinStreakReached": False,
            "isResetLoseStreakReached": False,
            "isResetProfitReached": False,
            "isResetLossReached": False,
            "isBetInterrupted": False,

            # Internal
            "stop_requested": False,
            "need_rotate": False,
            "rotate_seed": None,
        }

        # Push defaults to LUA
        self._sync_to_lua(rw=True, ro=True)

        # Register functions
        g = self.lua.globals()
        g.stop = self._lua_stop
        g.resetseed = self._lua_resetseed
        g.round = lambda n, p: round(float(n), int(p))
        g.dobet = lambda: None  # No-op placeholder, called by engine

        # Execute the script
        try:
            self.lua.execute(script)
        except Exception as e:
            raise ValueError(f"LUA syntax error: {e}")

    def _sync_to_lua(self, rw=True, ro=True):
        """Sync state to LUA globals."""
        g = self.lua.globals()
        if rw:
            for k in LUA_RW_VARS:
                g[k] = self.s[k]
        if ro:
            for k in LUA_RO_VARS:
                if k == "lastBet":
                    g[k] = self._dict_to_lua_table(self.s[k])
                else:
                    g[k] = self.s[k]

    def _sync_from_lua(self):
        """Read RW vars from LUA back to state."""
        g = self.lua.globals()
        for k in LUA_RW_VARS:
            try:
                val = g[k]
                if val is not None:
                    self.s[k] = val
            except (KeyError, AttributeError):
                pass

    def _dict_to_lua_table(self, d: dict):
        """Convert Python dict to LUA table."""
        if not d:
            return {}
        t = self.lua.table_from(d)
        # Handle nested dicts
        for k, v in d.items():
            if isinstance(v, dict):
                t[k] = self._dict_to_lua_table(v)
            else:
                t[k] = v
        return t

    def _lua_stop(self):
        """LUA stop() function."""
        self.s["stop_requested"] = True

    def _lua_resetseed(self, seed=None):
        """LUA resetseed(seed) function."""
        self.s["need_rotate"] = True
        self.s["rotate_seed"] = str(seed) if seed else "__auto__"
        self.s["seedChanged"] = True
        self._sync_to_lua(rw=False, ro=True)
        return True

    def update_before_bet(self, state_update: dict):
        """Update RO vars before a bet, then call dobet()."""
        self.s.update(state_update)
        self._sync_to_lua(rw=False, ro=True)

        # Call dobet()
        try:
            self.lua.globals().dobet()
        except Exception as e:
            raise RuntimeError(f"LUA dobet() error: {e}")

        # Read back RW vars
        self._sync_from_lua()

    def set_after_bet(self, state_update: dict):
        """Update state after a bet result comes in."""
        self.s.update(state_update)
        self._sync_to_lua(rw=False, ro=True)

    def should_stop(self) -> bool:
        return self.s["stop_requested"]

    def needs_seed_rotation(self):
        if self.s["need_rotate"]:
            return True, self.s["rotate_seed"]
        return False, None

    def reset_seed_rotated(self):
        self.s["need_rotate"] = False
        self.s["rotate_seed"] = None
        self._sync_to_lua(rw=False, ro=True)
