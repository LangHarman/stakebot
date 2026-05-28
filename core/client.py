"""
Stake.com API client wrapper — pure aiohttp, no stakeapi/cryptography needed.
Handles auth, mirror domains, GraphQL betting, and session management.
"""
import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiohttp


@dataclass
class StakeConfig:
    """Bot configuration."""
    access_token: str = ""
    session_cookie: str = ""
    base_url: str = "https://stake.com"
    mirror_mode: bool = False
    config_path: Path = Path.home() / ".stakebot" / "config.json"


class StakeConfigManager:
    """Manage configuration file."""

    @staticmethod
    def load(path: Optional[Path] = None) -> StakeConfig:
        path = path or StakeConfig.config_path
        if path.exists():
            data = json.loads(path.read_text())
            return StakeConfig(**data)
        return StakeConfig()

    @staticmethod
    def save(cfg: StakeConfig, path: Optional[Path] = None):
        path = path or StakeConfig.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "access_token": cfg.access_token,
            "session_cookie": cfg.session_cookie,
            "base_url": cfg.base_url,
            "mirror_mode": cfg.mirror_mode,
        }, indent=2))
        path.chmod(0o600)


class StakeClient:
    """
    Stake.com API client — pure aiohttp.
    No stakeapi/cryptography dependency needed.
    """

    def __init__(self, config: Optional[StakeConfig] = None):
        self.config = config or StakeConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {}

    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._headers = {
                "x-access-token": self.config.access_token,
                "Content-Type": "application/json",
                "Origin": self.base_url,
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Mobile Safari/537.36"
                ),
            }
            if self.config.session_cookie:
                self._headers["Cookie"] = f"session={self.config.session_cookie}"
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── GraphQL ─────────────────────────────────────────────

    async def _graphql_request(
        self,
        query: str,
        variables: dict = None,
        operation_name: str = None,
    ) -> dict:
        """Send a raw GraphQL request to Stake.com."""
        session = await self._get_session()
        url = f"{self.base_url}/_api/graphql"

        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        async with session.post(url, json=payload, headers=self._headers) as resp:
            if resp.status == 401:
                raise Exception("❌ Auth failed — token invalid/expired")
            if resp.status == 429:
                raise Exception("⏳ Rate limited — slow down")
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"HTTP {resp.status}: {text[:200]}")

            data = await resp.json()

            if "errors" in data:
                errors = [e.get("message", "?") for e in data["errors"]]
                raise Exception(f"GraphQL errors: {', '.join(errors)}")

            return data.get("data", {})

    # ── Auth / Balance ──────────────────────────────────────

    async def check_auth(self) -> bool:
        """Test if access token works."""
        try:
            data = await self._graphql_request("""
                query {
                    user {
                        id
                        name
                    }
                }
            """, operation_name="User")
            return data.get("user") is not None
        except Exception:
            return False

    async def get_balance_simple(self) -> dict:
        """Get simplified balance."""
        try:
            data = await self._graphql_request("""
                query UserBalances {
                    user {
                        balances {
                            available {
                                amount
                                currency
                            }
                        }
                    }
                }
            """, operation_name="UserBalances")

            user = data.get("user", {})
            balances = user.get("balances", {})
            available = balances.get("available", [])

            result = {}
            for bal in available:
                currency = bal.get("currency", "btc").lower()
                amount = float(bal.get("amount", 0))
                result[currency] = amount
            return result
        except Exception as e:
            return {"error": str(e)}

    # ── Dice ────────────────────────────────────────────────

    async def place_dice_bet(
        self,
        amount: float,
        target: float,
        over: bool,
    ) -> dict:
        """Place a Dice bet via GraphQL."""
        query = """
        mutation DicePlay($amount: Float!, $target: Float!, $over: Boolean!) {
            dicePlay(input: { amount: $amount, target: $target, over: $over }) {
                id amount payout multiplier outcome
                user { balance }
            }
        }
        """
        variables = {"amount": amount, "target": target, "over": over}

        try:
            data = await self._graphql_request(query, variables, "DicePlay")
            result = data.get("dicePlay", {})
            return {
                "id": result.get("id", ""),
                "amount": float(result.get("amount", 0)),
                "payout": float(result.get("payout", 0)),
                "multiplier": float(result.get("multiplier", 0)),
                "outcome": result.get("outcome", ""),
                "won": result.get("outcome") == "win",
                "balance_after": result.get("user", {}).get("balance"),
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Limbo ───────────────────────────────────────────────

    async def place_limbo_bet(
        self,
        amount: float,
        target_multiplier: float,
    ) -> dict:
        """Place a Limbo bet via GraphQL."""
        query = """
        mutation LimboPlay($amount: Float!, $targetMultiplier: Float!) {
            limboPlay(input: { amount: $amount, targetMultiplier: $targetMultiplier }) {
                id amount payout multiplier outcome
                crashMultiplier targetMultiplier
                user { balance }
            }
        }
        """
        variables = {"amount": amount, "targetMultiplier": target_multiplier}

        try:
            data = await self._graphql_request(query, variables, "LimboPlay")
            result = data.get("limboPlay", {})
            return {
                "id": result.get("id", ""),
                "amount": float(result.get("amount", 0)),
                "payout": float(result.get("payout", 0)),
                "multiplier": float(result.get("multiplier", 0)),
                "outcome": result.get("outcome", ""),
                "won": result.get("outcome") == "win",
                "balance_after": result.get("user", {}).get("balance"),
                "crash_point": float(result.get("crashMultiplier", 0)),
                "target_multiplier": float(result.get("targetMultiplier", 0)),
            }
        except Exception as e:
            return {"error": str(e)}


async def test_auth(token: str) -> bool:
    """Quick test if an access token works (default domain)."""
    cfg = StakeConfig(access_token=token)
    return await test_auth_from_config(cfg)

async def test_auth_from_config(cfg: StakeConfig) -> bool:
    """Test auth with a specific config (supports mirror domain)."""
    try:
        async with StakeClient(cfg) as client:
            return await client.check_auth()
    except Exception:
        return False


def get_token_from_browser_instructions() -> str:
    return """
╔══════════════════════════════════════════════════════════╗
║              CARA DAPATIN ACCESS TOKEN                   ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  1. Buka Stake.com (atau mirror) di Chrome/Firefox       ║
║  2. Login ke akun kamu                                   ║
║  3. F12 → tab Network                                    ║
║  4. Refresh halaman                                      ║
║  5. Cari request ke "/_api/graphql"                      ║
║  6. Header "x-access-token" → copy token-nya             ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    print(get_token_from_browser_instructions())
