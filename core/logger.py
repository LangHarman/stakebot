"""
Session Logger — records every bet to JSON for later analysis.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / ".stakebot" / "logs"


@dataclass
class BetRecord:
    bet_id: int
    timestamp: str
    game: str
    coin: str
    amount: float
    target: float
    condition: str
    won: bool
    payout: float
    profit: float
    streak: int
    balance: float
    result_raw: dict = field(default_factory=dict)


class SessionLogger:
    """Records every bet to a session log file."""

    def __init__(self, game: str, coin: str, base_bet: float,
                 script_name: str = ""):
        self.game = game
        self.coin = coin
        self.base_bet = base_bet
        self.script_name = script_name
        self.bets: list[BetRecord] = []
        self._start_time = datetime.now(timezone.utc)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def session_id(self) -> str:
        return self._start_time.strftime("%Y%m%d_%H%M%S")

    @property
    def path(self) -> Path:
        return LOG_DIR / f"session_{self.session_id}.json"

    def record(self, bet_id: int, amount: float, target: float,
               condition: str, won: bool, payout: float,
               profit: float, streak: int, balance: float,
               result_raw: dict = None):
        rec = BetRecord(
            bet_id=bet_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            game=self.game, coin=self.coin,
            amount=amount, target=target, condition=condition,
            won=won, payout=payout, profit=profit,
            streak=streak, balance=balance,
            result_raw=result_raw or {},
        )
        self.bets.append(rec)

    def summary(self) -> dict:
        """Return cumulative session stats."""
        total = len(self.bets)
        wins = sum(1 for b in self.bets if b.won)
        losses = total - wins
        profit = sum(b.profit for b in self.bets)
        return {
            "session_id": self.session_id,
            "game": self.game,
            "coin": self.coin,
            "base_bet": self.base_bet,
            "script": self.script_name,
            "started": self._start_time.isoformat(),
            "ended": datetime.now(timezone.utc).isoformat(),
            "total_bets": total,
            "wins": wins,
            "losses": losses,
            "winrate": round(wins / total * 100, 2) if total else 0,
            "profit": profit,
            "best_streak": max((b.streak for b in self.bets), default=0),
            "worst_streak": min((b.streak for b in self.bets), default=0),
            "biggest_bet": max((b.amount for b in self.bets), default=0),
        }

    def save(self):
        """Write session log to JSON file."""
        data = {
            "summary": self.summary(),
            "bets": [
                {
                    "id": b.bet_id,
                    "time": b.timestamp,
                    "amount": b.amount,
                    "target": b.target,
                    "condition": b.condition,
                    "won": b.won,
                    "payout": b.payout,
                    "profit": b.profit,
                    "streak": b.streak,
                    "balance": b.balance,
                }
                for b in self.bets
            ],
        }
        self.path.write_text(json.dumps(data, indent=2))


def list_sessions(n: int = 10) -> list[Path]:
    """Return most recent session log paths."""
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob("session_*.json"), reverse=True)[:n]


def read_summary(path: Path) -> dict:
    """Read summary from a session log."""
    data = json.loads(path.read_text())
    return data.get("summary", {})
