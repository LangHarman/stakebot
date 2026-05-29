"""
Betting engine for StakeBot.
Orchestrates the betting loop: read config → place bet → check stop conditions → repeat.
Uses the LUA scripting engine for strategy.
"""
import asyncio
import time
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field

from core.client import StakeClient
from core.script_engine import LuaScriptEngine


@dataclass
class BetConfig:
    """Betting configuration."""
    game_type: str = "dice"       # "dice" or "limbo"
    coin: str = "btc"
    base_bet: float = 0.00000001
    target: float = 49.5          # chance for dice, multiplier for limbo
    over: bool = True              # dice: bet high
    max_bet: float = 0.0          # 0 = no limit
    target_profit: float = 0.0     # stop when profit >= this
    target_loss: float = 0.0       # stop when loss >= this
    target_balance: float = 0.0    # stop when balance >= this
    max_bets: int = 0              # 0 = unlimited
    max_seconds: int = 0           # 0 = unlimited

    def to_dict(self) -> dict:
        return {
            "game_type": self.game_type,
            "coin": self.coin,
            "base_bet": self.base_bet,
            "target": self.target,
            "over": self.over,
            "max_bet": self.max_bet,
            "target_profit": self.target_profit,
            "target_loss": self.target_loss,
            "target_balance": self.target_balance,
            "max_bets": self.max_bets,
            "max_seconds": self.max_seconds,
        }


@dataclass
class BetStats:
    """Running statistics."""
    bets_placed: int = 0
    wins: int = 0
    losses: int = 0
    total_profit: float = 0.0
    total_wagered: float = 0.0
    largest_bet: float = 0.0
    largest_win: float = 0.0
    current_streak: int = 0
    start_balance: float = 0.0
    current_balance: float = 0.0
    start_time: float = 0.0
    last_bet_info: dict = field(default_factory=dict)

    def add_result(self, bet_result: dict):
        """Update stats with a bet result."""
        amount = bet_result.get("amount", 0)
        payout = bet_result.get("payout", 0)
        won = bet_result.get("won", False)

        self.bets_placed += 1
        self.total_wagered += amount

        if won:
            self.wins += 1
            profit = payout - amount
            self.total_profit += profit
            self.current_streak = abs(self.current_streak) + 1
            if payout > self.largest_win:
                self.largest_win = payout
        else:
            self.losses += 1
            self.total_profit -= amount
            self.current_streak = -abs(self.current_streak) - 1

        if amount > self.largest_bet:
            self.largest_bet = amount

        self.current_balance = bet_result.get("balance_after", self.current_balance)
        self.last_bet_info = bet_result

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> str:
        elapsed = self.elapsed_seconds()
        hours, rem = divmod(int(elapsed), 3600)
        mins, secs = divmod(rem, 60)
        time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

        roi = (self.total_profit / self.total_wagered * 100) if self.total_wagered > 0 else 0

        return (
            f"  ⏱ Elapsed: {time_str}   #️⃣ Bets: {self.bets_placed}\n"
            f"  ✅ Wins: {self.wins}   ❌ Losses: {self.losses}   📊 Streak: {self.current_streak:+d}\n"
            f"  💰 Profit: {self.total_profit:.8f}   ROI: {roi:+.2f}%\n"
            f"  🏆 Largest Bet: {self.largest_bet:.8f}   Largest Win: {self.largest_win:.8f}"
        )

    def short_line(self) -> str:
        elapsed = self.elapsed_seconds()
        return (
            f"[#{self.bets_placed}] "
            f"{'✅' if self.last_bet_info.get('won') else '❌'} "
            f"{'W' if self.last_bet_info.get('won') else 'L':>4} "
            f"S{self.current_streak:+d} "
            f"P{self.total_profit:+.8f} "
            f"B{self.current_balance:.8f}"
        )


class BettingEngine:
    """Main betting loop engine."""

    def __init__(self, client: StakeClient, config: BetConfig,
                 lua_engine: LuaScriptEngine = None,
                 on_bet_placed: Callable = None,
                 on_error: Callable = None):
        self.client = client
        self.config = config
        self.lua = lua_engine
        self.on_bet_placed = on_bet_placed
        self.on_error = on_error
        self.stats = BetStats()
        self._running = False

    async def run(self) -> BetStats:
        """Run the betting loop."""
        self._running = True
        self.stats.start_time = time.time()

        # Get initial balance
        await self._update_balance()

        if self.stats.current_balance <= 0:
            err_msg = f"⚠️ Balance is 0 (coin: {self.config.coin}). Check your wallet."
            if self.on_error:
                await self.on_error(err_msg)
            return self.stats

        self.stats.start_balance = self.stats.current_balance

        # Main loop
        while self._running:
            # ── Check global stop conditions ──
            if self.lua and self.lua.should_stop():
                break

            # Check max bets
            if self.config.max_bets > 0 and self.stats.bets_placed >= self.config.max_bets:
                break

            # Check max time
            if self.config.max_seconds > 0 and self.stats.elapsed_seconds() >= self.config.max_seconds:
                break

            # Check profit/loss targets
            if self.config.target_profit > 0 and self.stats.total_profit >= self.config.target_profit:
                break
            if self.config.target_loss > 0 and self.stats.total_profit <= -self.config.target_loss:
                break
            if self.config.target_balance > 0 and self.stats.current_balance >= self.config.target_balance:
                break

            # ── Determine bet amount using LUA ──
            if self.lua:
                try:
                    state_update = {
                        "balance": self.stats.current_balance,
                        "bets": self.stats.bets_placed,
                        "profit": self.stats.total_profit,
                        "wins": self.stats.wins,
                        "losses": self.stats.losses,
                        "currentstreak": self.stats.current_streak,
                        "previousbet": self.stats.last_bet_info.get("amount", 0),
                        "seedChanged": False,
                        "isFirstGreen": self.stats.last_bet_info.get("won", False) and self.stats.bets_placed > 1,
                        "isFirstRed": not self.stats.last_bet_info.get("won", True) and self.stats.bets_placed > 1,
                        "isResetProfitReached": False,
                        "isResetLossReached": False,
                        "isResetWinStreakReached": False,
                        "isResetLoseStreakReached": False,
                        "isMaxBetReached": False,
                    }

                    # Check reset conditions
                    if self.lua.s.get("resetIfProfit", 0) > 0 and self.stats.total_profit >= self.lua.s["resetIfProfit"]:
                        state_update["isResetProfitReached"] = True
                    if self.lua.s.get("resetIfLose", 0) > 0 and self.stats.total_profit <= -self.lua.s["resetIfLose"]:
                        state_update["isResetLossReached"] = True
                    if self.lua.s.get("resetIfWinStreak", 0) > 0 and self.stats.current_streak >= self.lua.s["resetIfWinStreak"]:
                        state_update["isResetWinStreakReached"] = True
                    if self.lua.s.get("resetIfLoseStreak", 0) > 0 and self.stats.current_streak <= -self.lua.s["resetIfLoseStreak"]:
                        state_update["isResetLoseStreakReached"] = True

                    # Check maxbet
                    if self.lua.s.get("maxbet", 0) > 0 and self.lua.s["nextbet"] > self.lua.s["maxbet"]:
                        state_update["isMaxBetReached"] = True

                    # Update LUA state and call dobet()
                    self.lua.update_before_bet(state_update)
                except Exception as e:
                    if self.on_error:
                        await self.on_error(f"LUA error: {e}")
                    break

                # Check stop after dobet
                if self.lua.should_stop():
                    break

                # Read bet params from LUA
                bet_amount = self.lua.s.get("nextbet", self.config.base_bet)
                bet_chance = self.lua.s.get("chance", self.config.target)
                bet_bethigh = self.lua.s.get("bethigh", self.config.over)
            else:
                # No LUA → use config values directly
                bet_amount = self.config.base_bet
                bet_chance = self.config.target
                bet_bethigh = self.config.over

            # Cap maxbet
            if self.config.max_bet > 0 and bet_amount > self.config.max_bet:
                bet_amount = self.config.max_bet

            # ── Place bet ──
            try:
                if self.config.game_type == "limbo":
                    result = await self.client.place_limbo_bet(
                        amount=bet_amount,
                        target_multiplier=bet_chance,
                        currency=self.config.coin,
                    )
                else:
                    result = await self.client.place_dice_bet(
                        amount=bet_amount,
                        target=bet_chance,
                        over=bet_bethigh,
                        currency=self.config.coin,
                    )

                if "error" in result:
                    if self.on_error:
                        await self.on_error(f"Bet error: {result['error']}")
                    # Brief pause before retry
                    await asyncio.sleep(1)
                    continue

                # Update stats
                self.stats.add_result(result)

            except Exception as e:
                if self.on_error:
                    await self.on_error(f"Exception: {e}")
                await asyncio.sleep(2)
                continue

            # ── Callback ──
            if self.on_bet_placed:
                await self.on_bet_placed(self.stats, result)

            # ── Handle seed rotation ──
            if self.lua:
                needs_rot, seed_val = self.lua.needs_seed_rotation()
                if needs_rot:
                    try:
                        await self._rotate_seed(seed_val)
                        self.lua.reset_seed_rotated()
                    except Exception as e:
                        if self.on_error:
                            await self.on_error(f"Seed rotation error: {e}")

            # Small delay to prevent rate limiting
            await asyncio.sleep(0.3)

        return self.stats

    async def stop(self):
        """Stop the betting loop."""
        self._running = False
        if self.lua:
            self.lua.s["stop_requested"] = True

    async def _update_balance(self):
        """Fetch current balance from Stake."""
        balances = await self.client.get_balance_simple()
        if isinstance(balances, dict) and "error" not in balances:
            coin_balance = balances.get(self.config.coin, 0)
            self.stats.current_balance = float(coin_balance)

    async def _rotate_seed(self, seed_val: str):
        """Rotate the client seed for provably fair."""
        # Seed rotation mutation from Taraje
        seed = seed_val if seed_val != "__auto__" else None
        if seed is None:
            import secrets
            seed = secrets.token_hex(16)

        query = """
        mutation RotateSeedPair($seed: String!) {
            rotateSeedPair(seed: $seed) {
                clientSeed {
                    user { id name }
                }
            }
        }
        """
        try:
            await self.client._graphql_request(query, {"seed": seed})
        except Exception as e:
            raise Exception(f"Seed rotation failed: {e}")
