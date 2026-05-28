"""
Betting engine - handles the core loop for both manual and script modes.
Manages bet lifecycle, stop conditions, and statistics tracking.
"""
import time
import signal
import sys
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BetStats:
    """Track betting statistics."""
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    total_wagered: float = 0.0
    total_payout: float = 0.0
    net_profit: float = 0.0
    current_streak: int = 0  # positive = win streak, negative = loss streak
    biggest_win: float = 0.0
    biggest_loss: float = 0.0
    start_balance: float = 0.0
    current_balance: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.total_bets == 0:
            return 0.0
        return (self.wins / self.total_bets) * 100

    @property
    def profit(self) -> float:
        return self.net_profit

    def record_bet(self, amount: float, won: bool, payout: float):
        self.total_bets += 1
        self.total_wagered += amount

        if won:
            self.wins += 1
            self.total_payout += payout
            net = payout - amount
            self.net_profit += net
            self.current_streak = self.current_streak + 1 if self.current_streak >= 0 else 1
            if payout > self.biggest_win:
                self.biggest_win = payout
        else:
            self.losses += 1
            self.net_profit -= amount
            self.current_streak = self.current_streak - 1 if self.current_streak <= 0 else -1
            if amount > self.biggest_loss:
                self.biggest_loss = amount


@dataclass
class StopConditions:
    """Bot stop conditions."""
    max_bets: int = 0          # 0 = unlimited
    target_profit: float = 0.0 # 0 = no target
    max_loss: float = 0.0      # 0 = no limit
    max_streak: int = 0        # 0 = no limit
    max_balance: float = 0.0   # 0 = no limit
    min_balance: float = 0.0   # 0 = no limit


@dataclass
class BetConfig:
    """Bet configuration."""
    game_type: str = "dice"  # "dice" or "limbo"
    base_bet: float = 0.000001
    currency: str = "btc"
    chance: float = 49.5
    payout_multiplier: float = 0.0  # Auto-calculated from chance if 0
    bet_high: bool = True
    on_win: str = "reset"
    on_loss: str = "reset"
    increase_pct: float = 100.0
    decrease_pct: float = 0.0

    # Limbo-specific
    target_multiplier: float = 2.0  # Limbo target (overrides chance)

    def get_payout(self) -> float:
        if self.payout_multiplier > 0:
            return self.payout_multiplier
        if self.game_type == "limbo":
            return self.target_multiplier
        if self.chance <= 0:
            return 2.0
        return round((99.0 / self.chance) * 0.99, 4)

    def get_target(self) -> float:
        """Get the target parameter for betting.
        - Dice: target number (0-100)
        - Limbo: target multiplier
        """
        if self.game_type == "limbo":
            return self.target_multiplier
        if self.bet_high:
            return round(100 - (self.chance * 100 / 100), 2)
        else:
            return round(self.chance * 100 / 100, 2)

    def get_direction(self) -> bool:
        """Get bet direction. Only relevant for dice."""
        return self.bet_high


class BettingEngine:
    """
    Core betting engine.
    Runs the betting loop, manages stop conditions, and
    calls the strategy callback after each result.
    """

    def __init__(
        self,
        place_bet_fn: Callable,
        get_balance_fn: Callable,
    ):
        """
        Args:
            place_bet_fn: async callable(amount, target, over) -> dict
            get_balance_fn: async callable() -> dict
        """
        self.place_bet = place_bet_fn
        self.get_balance = get_balance_fn
        self.stats = BetStats()
        self.stop_conditions = StopConditions()
        self.config = BetConfig()
        self.running = False
        self.paused = False
        self._strategy_fn: Optional[Callable] = None
        self._on_result_fn: Optional[Callable] = None
        self._abort = False

        # LUA script context (used by script mode)
        self.script_context = {}

    def set_strategy(self, fn: Callable):
        """
        Set strategy callback.
        Called after each bet result with (won, amount, payout, stats).
        Should return dict with optional overrides: nextbet, chance, high
        """
        self._strategy_fn = fn

    def on_result(self, fn: Callable):
        """Set result callback for UI updates."""
        self._on_result_fn = fn

    def check_stop_conditions(self) -> Optional[str]:
        """Check all stop conditions. Returns reason string or None."""
        if self._abort:
            return "Manual abort"

        s = self.stats
        c = self.stop_conditions

        if c.max_bets > 0 and s.total_bets >= c.max_bets:
            return f"Max bets reached ({c.max_bets})"

        if c.target_profit > 0 and s.net_profit >= c.target_profit:
            return f"Target profit reached (${c.target_profit})"

        if c.max_loss > 0 and s.net_profit <= -c.max_loss:
            return f"Max loss reached (${c.max_loss})"

        if c.max_streak > 0 and abs(s.current_streak) >= c.max_streak:
            direction = "win" if s.current_streak > 0 else "loss"
            return f"Max {direction} streak reached ({abs(s.current_streak)})"

        if c.max_balance > 0 and s.current_balance >= c.max_balance:
            return f"Max balance reached (${c.max_balance})"

        if c.min_balance > 0 and s.current_balance <= c.min_balance:
            return f"Min balance reached (${c.min_balance})"

        return None

    def get_next_bet(self, won: bool) -> dict:
        """
        Calculate next bet based on manual config.
        Returns dict: {amount, target, over}
        """
        cfg = self.config

        # Start with base bet
        if self.stats.total_bets == 0:
            next_amount = cfg.base_bet
        else:
            if won:
                if cfg.on_win == "reset":
                    next_amount = cfg.base_bet
                elif cfg.on_win == "increase":
                    next_amount = self._last_amount * (1 + cfg.increase_pct / 100)
                elif cfg.on_win == "decrease":
                    next_amount = self._last_amount * (1 - cfg.decrease_pct / 100)
                else:  # same
                    next_amount = self._last_amount
            else:
                if cfg.on_loss == "reset":
                    next_amount = cfg.base_bet
                elif cfg.on_loss == "increase":
                    next_amount = self._last_amount * (1 + cfg.increase_pct / 100)
                elif cfg.on_loss == "decrease":
                    next_amount = self._last_amount * (1 - cfg.decrease_pct / 100)
                else:  # same
                    next_amount = self._last_amount

        target = cfg.get_target()
        return {
            "amount": round(next_amount, 8),
            "target": target,
            "over": cfg.bet_high,
            "game_type": cfg.game_type,
        }

    async def run(self):
        """
        Main betting loop.
        """
        self.running = True
        self.paused = False
        self._abort = False

        # Get initial balance
        try:
            balance_data = await self.get_balance()
            if isinstance(balance_data, dict):
                bal = balance_data.get("available", 0) or balance_data.get("btc", 0)
                self.stats.start_balance = float(bal)
                self.stats.current_balance = float(bal)
        except Exception as e:
            print(f"[!] Failed to get initial balance: {e}")
            self.running = False
            return

        game_label = "Limbo" if self.config.game_type == "limbo" else "Dice"
        param_label = f"{self.config.target_multiplier}x" if self.config.game_type == "limbo" else f"{self.config.chance}%"
        print(f"\n🚀 Starting {game_label} bot — Balance: {self.stats.start_balance:.8f}")
        print(f"   Base bet: {self.config.base_bet} | Target: {param_label}")
        print(f"   Stop conditions: {self._stop_summary()}")
        print("─" * 50)

        self._last_amount = self.config.base_bet

        while self.running and not self._abort:
            # Check for pause
            if self.paused:
                await asyncio.sleep(0.5)
                continue

            # Check stop conditions
            reason = self.check_stop_conditions()
            if reason:
                print(f"\n⏹️  Stopped: {reason}")
                break

            # Determine next bet
            bet_info = None
            if self._strategy_fn:
                # Strategy function returns overrides
                try:
                    bet_info = self._strategy_fn(self.stats)
                except StopIteration:
                    print("\n⏹️  Script requested stop")
                    break
                except Exception as e:
                    print(f"[!] Strategy error: {e}")
                    break

            if bet_info is None:
                bet_info = self.get_next_bet(self.stats.total_bets > 0 and self._last_won if hasattr(self, '_last_won') else False)

            amount = bet_info.get("amount", self.config.base_bet)
            target = bet_info.get("target", self.config.get_target())
            over = bet_info.get("over", self.config.bet_high)
            game_type = bet_info.get("game_type", self.config.game_type)

            self._last_amount = amount

            # Place bet (dice or limbo)
            try:
                if game_type == "limbo":
                    result = await self.place_bet(
                        amount=amount,
                        target_multiplier=target,
                    )
                else:
                    result = await self.place_bet(
                        amount=amount,
                        target=target,
                        over=over,
                    )
            except Exception as e:
                print(f"[!] Bet failed: {e}")
                await asyncio.sleep(2)
                continue

            if "error" in result:
                print(f"[!] Bet error: {result['error']}")
                await asyncio.sleep(2)
                continue

            won = result.get("won", False)
            payout = result.get("payout", 0)
            self._last_won = won

            # Update stats
            self.stats.record_bet(amount, won, payout)

            # Update balance from result if available
            if result.get("balance_after"):
                self.stats.current_balance = float(result["balance_after"])

            # Show result
            icon = "🟢" if won else "🔴"
            multiplier = result.get("multiplier", 0)
            profit_str = f"{payout - amount:+.8f}" if won else f"{-amount:.8f}"

            if game_type == "limbo":
                crash = result.get("crash_point", 0)
                target_m = result.get("target_multiplier", target)
                extra = f"crash={crash:.2f}x target={target_m:.2f}x"
            else:
                extra = f"x{multiplier:.2f}"

            print(f"#{self.stats.total_bets:>5} {icon} {amount:.8f} → "
                  f"{'WON' if won else 'LOST':>4} "
                  f"({extra}) "
                  f"P/L: {profit_str} "
                  f"| Balance: {self.stats.current_balance:.8f}")

            # Call result callback
            if self._on_result_fn:
                self._on_result_fn(won, amount, payout, self.stats)

            # Small delay between bets (avoid rate limits)
            await asyncio.sleep(0.5)

        # Final summary
        self.running = False
        self._print_summary()

    def _stop_summary(self) -> str:
        c = self.stop_conditions
        parts = []
        if c.max_bets > 0:
            parts.append(f"max {c.max_bets} bets")
        if c.target_profit > 0:
            parts.append(f"target +{c.target_profit}")
        if c.max_loss > 0:
            parts.append(f"max -{c.max_loss}")
        return ", ".join(parts) if parts else "none"

    def _print_summary(self):
        s = self.stats
        roi = (s.net_profit / s.total_wagered * 100) if s.total_wagered > 0 else 0
        print("\n" + "═" * 50)
        print("📊  FINAL STATISTICS")
        print("═" * 50)
        print(f"  Total Bets:     {s.total_bets}")
        print(f"  Wins:           {s.wins} ({s.win_rate:.1f}%)")
        print(f"  Losses:         {s.losses} ({(100 - s.win_rate):.1f}%)")
        print(f"  Total Wagered:  {s.total_wagered:.8f}")
        print(f"  Total Payout:   {s.total_payout:.8f}")
        print(f"  Net Profit:     {s.net_profit:+.8f}")
        print(f"  ROI:            {roi:+.2f}%")
        print(f"  Best Win:       {s.biggest_win:.8f}")
        print(f"  Worst Loss:     {s.biggest_loss:.8f}")
        print(f"  Start Balance:  {s.start_balance:.8f}")
        print(f"  End Balance:    {s.current_balance:.8f}")
        print("═" * 50)

    def pause(self):
        self.paused = True
        print("⏸️  Paused")

    def resume(self):
        self.paused = False
        print("▶️  Resumed")

    def stop(self):
        self._abort = True
        print("⏹️  Stopping...")


# Allow graceful shutdown with keyboard
_engine_instance = None
def _signal_handler(sig, frame):
    global _engine_instance
    print("\n\n⚠️  Interrupt received, stopping...")
    if _engine_instance:
        _engine_instance.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, _signal_handler)
