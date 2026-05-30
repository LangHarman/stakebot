"""
Betting Engine — continuous loop with optional LUA scripting.

Drives the betting cycle: init LUA → run dobet() → place bet → 
parse result → update stats → run dobet() again.
"""
from __future__ import annotations

import asyncio
import time
import random
import string
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from .client import StakeClient, StakeError, AuthError, ConnectionError


@dataclass
class BetConfig:
    """Configuration for a betting session."""
    game: str = "dice"        # "dice", "limbo", or "crash"
    coin: str = "usdt"        # lowercase
    base_bet: float = 0.0001
    target: float = 49.5      # chance% (dice) or multiplier (limbo/crash)
    condition: str = "above"  # "above" or "below" (dice only)
    max_bets: int = 0         # 0 = unlimited
    stop_profit: float = 0.0  # 0 = no stop
    stop_loss: float = 0.0    # 0 = no stop
    on_win_reset: bool = True  # reset to base bet after win (web mode)
    on_win_pct: float = 0.0    # increase% on win (web mode)
    on_lose_reset: bool = False
    on_lose_pct: float = 100.0  # increase% on loss (martingale default)
    script_path: str = ""
    on_bet: Optional[Callable[["BetStats", dict], Awaitable[None]]] = None
    on_error: Optional[Callable[[str], Awaitable[None]]] = None


@dataclass
class BetStats:
    """Live betting session stats."""
    bets: int = 0
    wins: int = 0
    losses: int = 0
    profit: float = 0.0
    total_wagered: float = 0.0
    streak: int = 0  # positive=win streak, negative=loss streak
    best_streak: int = 0
    worst_streak: int = 0
    biggest_bet: float = 0.0
    start_balance: float = 0.0
    current_balance: float = 0.0

    winrate: float = 0.0

    def record(self, amount: float, payout: float, won: bool):
        self.bets += 1
        self.total_wagered += amount
        pnl = (payout - amount) if won else -amount
        self.profit += pnl

        if won:
            self.wins += 1
            self.streak = self.streak + 1 if self.streak > 0 else 1
        else:
            self.losses += 1
            self.streak = self.streak - 1 if self.streak < 0 else -1

        self.best_streak = max(self.best_streak, self.streak)
        self.worst_streak = min(self.worst_streak, self.streak)
        self.biggest_bet = max(self.biggest_bet, amount)
        self.winrate = (self.wins / self.bets * 100) if self.bets else 0


class BettingEngine:
    """Main betting loop with optional LUA scripting.

    Simple usage (no LUA):
        engine = BettingEngine(client, config)
        stats = await engine.run()

    With LUA:
        engine = BettingEngine(client, config, lua_engine=my_lua)
        stats = await engine.run()
    """

    def __init__(self, client: StakeClient, config: BetConfig,
                 lua_engine=None):
        self.client = client
        self.cfg = config
        self.lua = lua_engine
        self.stats = BetStats()
        self._running = False
        self._current_bet = config.base_bet
        self._last_won = False

    async def run(self, initial_balance: float | None = None) -> BetStats:
        """Run the betting loop. Returns final stats when stopped.

        Args:
            initial_balance: skip get_user() if provided (for loop mode).
        """
        self._running = True

        # Init balance
        if initial_balance is not None:
            self.stats.current_balance = initial_balance
            self.stats.start_balance = initial_balance
        else:
            try:
                user = await self.client.get_user()
                self.stats.current_balance = self.client.balance.get(
                    self.cfg.coin, 0)
                self.stats.start_balance = self.stats.current_balance
            except AuthError:
                raise
            except Exception:
                # Don't silently use 0 — raise so caller can handle
                raise ConnectionError("Gagal fetch balance — cek koneksi")

        # Init LUA
        if self.lua:
            self._init_lua()

        # Seed rotation (Taraje rotates on start)
        try:
            await self._rotate_seed()
        except Exception:
            pass

        # Main betting loop
        while self._running:
            # Check stop conditions
            reason = self._check_stop()
            if reason:
                break

            # Determine next bet via LUA or defaults
            amount, target, condition = self._next_bet()
            if amount is None:  # LUA called stop()
                break

            # Safety: don't bet more than balance
            if amount > self.stats.current_balance:
                if self.cfg.on_error:
                    await self.cfg.on_error(
                        f"Bet {amount:.8f} > balance {self.stats.current_balance:.8f}"
                    )
                break

            # Place bet (retry on transient errors, max 3 attempts)
            for attempt in range(3):
                try:
                    result = await self._place_bet(amount, target, condition)
                    won = result.get("won", False)
                    payout = result.get("payout", 0)
                    self._last_won = won

                    self.stats.record(amount, payout, won)

                    # Update LUA state
                    if self.lua:
                        self._update_lua(won, amount, payout, result)

                    # Callback
                    if self.cfg.on_bet:
                        await self.cfg.on_bet(self.stats, result)

                    break  # success, exit retry loop

                except AuthError as e:
                    if self.cfg.on_error:
                        await self.cfg.on_error(f"Auth: {e}")
                    self._running = False
                    break  # break retry loop; outer loop also stops (self._running=False)
                except Exception as e:
                    if self.cfg.on_error:
                        await self.cfg.on_error(f"Bet error (attempt {attempt+1}/3): {e}")
                    if attempt < 2:
                        await asyncio.sleep(1)
            else:
                # All retries failed — stop engine
                self._running = False
                break

        self._running = False
        return self.stats

    def stop(self):
        """Signal the engine to stop after current bet."""
        self._running = False

    # ── Internal ──

    async def _place_bet(self, amount: float, target: float,
                         condition: str) -> dict:
        """Place a bet and parse the response."""
        if self.cfg.game == "dice":
            data = await self.client.roll_dice(
                amount, target, condition, self.cfg.coin)
            roll = data.get("diceRoll", {})
            state = roll.get("state", {})
            result_num = float(state.get("result", 0))
            won = (
                (condition == "above" and result_num > target)
                or (condition == "below" and result_num < target)
            )
            return {
                "won": won,
                "payout": float(roll.get("payout", 0)),
                "result": result_num,
                "nonce": roll.get("nonce"),
                "id": roll.get("id"),
            }
        elif self.cfg.game == "limbo":
            data = await self.client.bet_limbo(
                amount, target, self.cfg.coin)
            bet = data.get("limboBet", {})
            state = bet.get("state", {})
            crash = float(state.get("result", 0))
            won = crash >= target
            return {
                "won": won,
                "payout": float(bet.get("payout", 0)),
                "crash_point": crash,
                "nonce": bet.get("nonce"),
                "id": bet.get("id"),
            }
        else:  # crash
            data = await self.client.bet_crash(
                amount, target, self.cfg.coin)
            bet = data.get("crashBet", {})
            state = bet.get("state", {})
            crash_point = float(state.get("result", 0))
            won = crash_point >= target
            return {
                "won": won,
                "payout": float(bet.get("payout", 0)),
                "crash_point": crash_point,
                "nonce": bet.get("nonce"),
                "id": bet.get("id"),
            }

    async def _rotate_seed(self):
        """Generate and set a random client seed string."""
        seed = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        await self.client.rotate_seed(seed)

    def _check_stop(self) -> str | None:
        """Return stop reason or None."""
        if self.cfg.max_bets > 0 and self.stats.bets >= self.cfg.max_bets:
            return "max_bets"
        if self.cfg.stop_profit > 0 and self.stats.profit >= self.cfg.stop_profit:
            return "target_profit"
        if self.cfg.stop_loss > 0 and self.stats.profit <= -self.cfg.stop_loss:
            return "stop_loss"
        return None

    def _next_bet(self) -> tuple[float | None, float, str]:
        """Determine next bet: (amount, target, condition).
        Returns (None, *, *) to stop.
        """
        if self.lua:
            nextbet = self.lua.get("nextbet", self.cfg.base_bet)
            target = self.lua.get("chance", self.cfg.target)
            bethigh = self.lua.get("bethigh", True)
            condition = "above" if bethigh else "below"
            # Run user's dobet()
            self.lua.call("dobet")
            # Check if stop() was called
            if self.lua.stopped:
                return None, target, condition
            # re-read after dobet() may have changed them
            amount = self.lua.get("nextbet", self.cfg.base_bet)
            target = self.lua.get("chance", target)
            return amount, target, condition

        # Web-based auto-bet mode
        if self.stats.bets > 0:
            if self._last_won:
                if self.cfg.on_win_reset:
                    self._current_bet = self.cfg.base_bet
                else:
                    self._current_bet *= (1 + self.cfg.on_win_pct / 100)
            else:
                if self.cfg.on_lose_reset:
                    self._current_bet = self.cfg.base_bet
                else:
                    self._current_bet *= (1 + self.cfg.on_lose_pct / 100)
        return self._current_bet, self.cfg.target, self.cfg.condition

    def _init_lua(self):
        """Initialize LUA engine with game variables."""
        l = self.lua
        l.set("basebet", self.cfg.base_bet)
        l.set("nextbet", self.cfg.base_bet)
        l.set("previousbet", self.cfg.base_bet)
        l.set("chance", self.cfg.target)
        l.set("bethigh", self.cfg.condition == "above")
        l.set("balance", self.stats.current_balance)
        l.set("profit", 0.0)
        l.set("currentstreak", 0.0)
        l.set("wins", 0)
        l.set("losses", 0)
        l.set("bets", 0)
        l.set("win", False)
        l.set("isFirstGreen", False)
        l.set("isFirstRed", False)
        l.set("isResetProfitReached", False)
        l.set("isMaxBetReached", False)
        l.set("isBetInterrupted", False)
        l.set("maxbet", 0)
        l.set("stopBetting", False)
        # Run user's init code (e.g., chance = 49.5)
        l.call("init")
        l.stopped = False

    def _update_lua(self, won: bool, amount: float, payout: float,
                    result: dict):
        """Update LUA state after a bet result."""
        l = self.lua
        prev_streak = l.get("currentstreak", 0)
        new_streak = prev_streak + 1 if won else (prev_streak - 1 if prev_streak > 0 else -1)

        l.set("win", won)
        l.set("previousbet", amount)
        l.set("balance", self.stats.current_balance)
        l.set("profit", self.stats.profit)
        l.set("currentstreak", new_streak)
        l.set("wins", self.stats.wins)
        l.set("losses", self.stats.losses)
        l.set("bets", self.stats.bets)

        # Streak flags
        l.set("isFirstGreen", not won and l.get("isFirstGreen", False))
        l.set("isFirstRed", won and l.get("isFirstRed", False))
        if won and prev_streak <= 0:
            l.set("isFirstGreen", True)
        if not won and prev_streak >= 0:
            l.set("isFirstRed", True)
