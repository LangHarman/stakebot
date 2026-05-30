"""
Stake.com API client — exact Taraje 2.8.0 GraphQL mutations.

Handles: auth (x-access-token), mirror domains, betting, WebSocket.
All mutations reverse-engineered from taraje/lib/Stake/_api.c (Cython-compiled).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

import aiohttp

# Known Stake mirrors (from Taraje + community)
MIRRORS: list[str] = [
    "https://stake.com",
    "https://stake.mba",
    "https://playstake.club",
    "https://stake.bz",
    "https://stake.us",
    "https://stake.to",
    "https://stake.ai",
]

# ── Exact Taraje 2.8.0 GraphQL operations ──

# Dice roll — note: $target (chance), $condition (above/below enum)
GQL_DICE_ROLL = """mutation DiceRoll(
  $amount: Float!
  $target: Float!
  $condition: CasinoGameDiceConditionEnum!
  $currency: CurrencyEnum!
  $identifier: String!
) {
  diceRoll(
    amount: $amount
    target: $target
    condition: $condition
    currency: $currency
    identifier: $identifier
  ) {
    id
    active
    amount
    payout
    payoutMultiplier
    currency
    game
    nonce
    state {
      ... on CasinoGameDice {
        result
        target
        condition
      }
    }
  }
}"""

# Limbo bet — note: $multiplierTarget (NOT just "multiplier")
GQL_LIMBO_BET = """mutation LimboBet(
  $amount: Float!
  $multiplierTarget: Float!
  $currency: CurrencyEnum!
  $identifier: String!
) {
  limboBet(
    amount: $amount
    multiplierTarget: $multiplierTarget
    currency: $currency
    identifier: $identifier
  ) {
    id
    active
    amount
    payout
    payoutMultiplier
    currency
    game
    nonce
    state {
      ... on CasinoGameLimbo {
        result
        multiplierTarget
      }
    }
  }
}"""

# Crash bet — similar pattern to Limbo
GQL_CRASH_BET = """mutation CrashBet(
  $amount: Float!
  $multiplierTarget: Float!
  $currency: CurrencyEnum!
  $identifier: String!
) {
  crashBet(
    amount: $amount
    multiplierTarget: $multiplierTarget
    currency: $currency
    identifier: $identifier
  ) {
    id
    active
    amount
    payout
    payoutMultiplier
    currency
    game
    nonce
    state {
      ... on CasinoGameCrash {
        result
        multiplierTarget
      }
    }
  }
}"""

# Rotate seed pair (Taraje calls this on every new seed)
GQL_ROTATE_SEED = """mutation RotateSeedPair($seed: String!) {
  rotateSeedPair(seed: $seed) {
    clientSeed { user { id name } }
  }
}"""

# Get full user info (balance, seeds, KYC tier, roles)
GQL_USER = """query InitialUserRequest {
  user {
    id
    name
    email
    createdAt
    roles { name }
    balances { available { amount currency } vault { amount currency } }
    activeClientSeed { id seed }
    activeServerSeed { id seedHash nextSeedHash nonce }
    previousServerSeed { id active blocked seed seedHash nonce }
  }
}"""

# House bet subscription (WebSocket)
GQL_HOUSE_BETS = """subscription HouseBets {
  houseBets {
    id
    iid
    type
    scope
    game { name }
    bet {
      id
      active
      amount
      payout
      currency
      game
      nonce
      state {
        ... on CasinoGameDice { result target condition }
        ... on CasinoGameLimbo { result multiplierTarget }
      }
    }
  }
}"""

# ── Config ──

CONFIG_DIR = Path.home() / ".stakebot"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class StakeConfig:
    access_token: str = ""
    session_cookie: str = ""
    base_url: str = "https://stake.com"
    mirror_mode: bool = True  # auto-try all mirrors
    proxy: str = ""

    @classmethod
    def load(cls, path: str | Path | None = None) -> "StakeConfig":
        p = Path(path) if path else CONFIG_PATH
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text())
            return cls(
                access_token=data.get("access_token", ""),
                session_cookie=data.get("session_cookie", ""),
                base_url=data.get("base_url", "https://stake.com"),
                mirror_mode=data.get("mirror_mode", True),
                proxy=data.get("proxy", ""),
            )
        except Exception:
            return cls()

    def save(self, path: str | Path | None = None):
        p = Path(path) if path else CONFIG_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "access_token": self.access_token,
            "session_cookie": self.session_cookie,
            "base_url": self.base_url,
            "mirror_mode": self.mirror_mode,
            "proxy": self.proxy,
        }, indent=2))
        p.chmod(0o600)

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token)


# ── cURL parser ──

def parse_curl(text: str) -> dict:
    """Parse 'Copy as cURL' from browser DevTools into config fields."""
    result: dict[str, str] = {}
    # URL
    m = re.search(r"curl\s+'([^']+)'", text)
    if m:
        result["url"] = m.group(1)
    # Headers
    for h in re.findall(r"-H\s+'([^']+)'", text):
        if ": " in h:
            k, v = h.split(": ", 1)
            kl = k.lower()
            if kl == "x-access-token":
                result["access_token"] = v
            elif kl == "cookie":
                result["session_cookie"] = v
    return result


# ── Stake API Client ──

class StakeClient:
    """Async client for Stake.com GraphQL API.

    Usage:
        async with StakeClient(cfg) as client:
            user = await client.get_user()
            result = await client.roll_dice(0.00001, 49.5, "above", "usdt")
    """

    def __init__(self, config: StakeConfig):
        self.cfg = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._working_url: str = ""  # cached working mirror
        self.balance: dict[str, float] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=5, force_close=False)
            kwargs = {"connector": connector}
            if self.cfg.proxy:
                kwargs["proxy"] = self.cfg.proxy
            self._session = aiohttp.ClientSession(**kwargs)
        return self._session

    def _headers(self) -> dict:
        h = {
            "x-access-token": self.cfg.access_token,
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Mobile Safari/537.36"
            ),
        }
        if self.cfg.session_cookie:
            h["Cookie"] = self.cfg.session_cookie
        return h

    async def _try_url(self, base: str, query: str, variables: dict,
                       op_name: str = "") -> Optional[dict]:
        """Try a single mirror URL."""
        url = base.rstrip("/") + "/_api/graphql"
        payload = {"query": query, "variables": variables}
        if op_name:
            payload["operationName"] = op_name

        try:
            async with self.session.post(
                url, json=payload, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "errors" in data:
                        err = data["errors"][0].get("message", str(data["errors"]))
                        if "unauthorized" in err.lower() or "token" in err.lower():
                            raise AuthError(err)
                        raise APIError(err)
                    return data.get("data")
                elif resp.status == 429:
                    return None  # rate limited, try next mirror
                else:
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    def _mirrors(self) -> list[str]:
        """Resolved mirror list based on config."""
        if self.cfg.mirror_mode:
            # Start with base_url or working_url, then try all mirrors
            start = self._working_url or self.cfg.base_url
            urls = [start] if start else []
            urls += [m for m in MIRRORS if m not in urls]
            return urls
        return [self.cfg.base_url]

    async def _query(self, query: str, variables: dict = None,
                     op_name: str = "") -> dict:
        """Execute a GraphQL query, trying all mirrors."""
        variables = variables or {}
        last_err = None

        for base in self._mirrors():
            result = await self._try_url(base, query, variables, op_name)
            if result is not None:
                self._working_url = base
                return result
            # tiny delay between mirror attempts
            await asyncio.sleep(0.2)

        raise ConnectionError(
            f"Gagal connect ke semua mirror ({len(self._mirrors())} dicoba).\n"
            "Coba: VPN / proxy / python main.py curl"
        )

    # ── Public API ──

    async def get_user(self) -> dict:
        """Get full user info (balances, seeds, KYC). Returns dict or raises."""
        data = await self._query(GQL_USER, op_name="InitialUserRequest")
        if not data or "user" not in data:
            raise AuthError("Gagal ambil data user — token mungkin expired")
        u = data["user"]
        # Parse balances
        self.balance = {}
        for b in u.get("balances", []):
            for k in ("available", "vault"):
                entry = b.get(k, {})
                c = (entry.get("currency") or "").lower()
                a = float(entry.get("amount", 0))
                if c:
                    self.balance[c] = self.balance.get(c, 0) + a
        return u

    async def roll_dice(self, amount: float, target: float,
                        condition: str, currency: str) -> dict:
        """Place a Dice bet.

        Args:
            amount: bet amount in currency units
            target: chance % (e.g. 49.5)
            condition: "above" or "below"
            currency: lowercase coin code (usdt, ltc, btc, etc.)
        """
        return await self._query(
            GQL_DICE_ROLL,
            variables={
                "amount": amount,
                "target": target,
                "condition": condition,
                "currency": currency.lower(),
                "identifier": str(uuid.uuid4()),
            },
            op_name="DiceRoll",
        )

    async def bet_limbo(self, amount: float, multiplier_target: float,
                        currency: str) -> dict:
        """Place a Limbo bet.

        Args:
            amount: bet amount in currency units
            multiplier_target: target multiplier (e.g. 2.0, 1.01)
            currency: lowercase coin code
        """
        return await self._query(
            GQL_LIMBO_BET,
            variables={
                "amount": amount,
                "multiplierTarget": multiplier_target,
                "currency": currency.lower(),
                "identifier": str(uuid.uuid4()),
            },
            op_name="LimboBet",
        )

    async def bet_crash(self, amount: float, multiplier_target: float,
                        currency: str) -> dict:
        """Place a Crash bet.

        Args:
            amount: bet amount in currency units
            multiplier_target: target multiplier (e.g. 2.0)
            currency: lowercase coin code
        """
        return await self._query(
            GQL_CRASH_BET,
            variables={
                "amount": amount,
                "multiplierTarget": multiplier_target,
                "currency": currency.lower(),
                "identifier": str(uuid.uuid4()),
            },
            op_name="CrashBet",
        )

    async def rotate_seed(self, seed: str) -> dict:
        """Rotate client seed pair (Taraje calls this)."""
        return await self._query(
            GQL_ROTATE_SEED,
            variables={"seed": seed},
            op_name="RotateSeedPair",
        )


# ── Exceptions ──

class StakeError(Exception): pass
class AuthError(StakeError): pass
class APIError(StakeError): pass
class ConnectionError(StakeError): pass
