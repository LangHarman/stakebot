"""
LUA Script Engine — Taraje 2.8.0 compatible variables & functions.

Provides: basebet, nextbet, chance, bethigh, balance, profit, 
currentstreak, win, betcounter, dobet(), stop(), resetseed(), round().
"""
from __future__ import annotations

import random
import string

try:
    import lupa
except ImportError:
    lupa = None


class LuaScriptEngine:
    """Wrap a LUA script with Taraje-compatible variables and functions.

    Usage:
        lua = LuaScriptEngine(script_text)
        lua.call("init")      # runs LUA init()
        lua.set("balance", 100.0)
        lua.set("nextbet", 0.001)
        lua.call("dobet")     # user's betting logic
        next = lua.get("nextbet", 0.001)
    """

    def __init__(self, script: str):
        self.script = script
        self.stopped = False
        self._lua = None
        if lupa:
            self._lua = lupa.LuaRuntime(unpack_returned_tuples=True)
            self._setup()
        else:
            print("⚠️  lupa not installed — LUA scripts disabled.")
            print("   pip install lupa")

    def _setup(self):
        """Register Taraje-compatible globals and functions."""
        L = self._lua

        # Globals table
        L.execute("_G.taraje = {}")

        # Betting variables
        L.globals().basebet = 0.0
        L.globals().nextbet = 0.0
        L.globals().previousbet = 0.0
        L.globals().chance = 49.5
        L.globals().bethigh = True
        L.globals().balance = 0.0
        L.globals().profit = 0.0
        L.globals().currentstreak = 0.0
        L.globals().win = False
        L.globals().bets = 0
        L.globals().wins = 0
        L.globals().losses = 0
        L.globals().stopBetting = False
        L.globals().isFirstGreen = False
        L.globals().isFirstRed = False
        L.globals().isResetProfitReached = False
        L.globals().isMaxBetReached = False
        L.globals().isBetInterrupted = False
        L.globals().maxbet = 0.0

        # Functions
        def _stop():
            self.stopped = True
            L.globals().stopBetting = True

        def _resetseed():
            # Generate random 32-char client seed
            return "".join(random.choices(
                string.ascii_letters + string.digits, k=32))

        def _round(n, decimals=0):
            return round(float(n), decimals)

        L.globals().stop = _stop
        L.globals().resetseed = _resetseed
        L.globals().round = _round

        # Load user script
        try:
            L.execute(self.script)
        except Exception as e:
            print(f"⚠️  LUA error: {e}")
            self._lua = None

    # ── Public API ──

    def call(self, name: str):
        """Call a LUA function by name (e.g. dobet, init). Safe to call
        if LUA is disabled or function doesn't exist."""
        if self._lua is None:
            return
        try:
            fn = self._lua.globals()[name]
        except KeyError:
            return  # function not defined — fine
        try:
            if not callable(fn):
                print(f"⚠️  LUA [{name}]: is not a function (type={type(fn).__name__})")
                return
            fn()
        except Exception as e:
            print(f"⚠️  LUA [{name}]: {e}")

    def get(self, key: str, default=None):
        """Get a LUA global variable."""
        if self._lua is None:
            return default
        try:
            v = self._lua.globals()[key]
            return v if v is not None else default
        except (KeyError, Exception):
            return default

    def set(self, key: str, value):
        """Set a LUA global variable."""
        if self._lua is None:
            return
        try:
            self._lua.globals()[key] = value
        except Exception:
            pass
