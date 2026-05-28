"""
Stake.com API client wrapper - pure aiohttp, no stakeapi/cryptography needed.
Handles auth, mirror domains, GraphQL betting, and session management.
"""
import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiohttp


# Known working Stake.com mirrors
KNOWN_MIRRORS = [
    "https://stake.com",
    "https://stake.mba",
    "https://playstake.club",
    "https://stake.bz",
    "https://stake.us",
    "https://stake.to",
    "https://stake.ai",
]


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
        }, indent=2, ensure_ascii=False))
        path.chmod(0o600)


class StakeClient:
    """
    Stake.com API client - pure aiohttp.
    Auto fallback ke mirror kalo domain utama gagal.
    """

    def __init__(self, config: Optional[StakeConfig] = None):
        self.config = config or StakeConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {}
        self._actual_url = self.config.base_url.rstrip("/")

    @property
    def base_url(self) -> str:
        return self._actual_url

    def _resolve_mirror_list(self) -> list:
        """Return list of URLs to try, starting from config base_url."""
        cfg_url = self.config.base_url.rstrip("/")
        if self.config.mirror_mode:
            # Start with configured URL, then try other mirrors
            urls = [cfg_url]
            for m in KNOWN_MIRRORS:
                if m not in urls:
                    urls.append(m)
            return urls
        return [cfg_url]

    async def _try_graphql(self, url: str, query: str, variables: dict = None,
                           operation_name: str = None) -> dict:
        """Try a GraphQL request to a specific URL."""
        session = await self._get_session()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        async with session.post(url, json=payload, headers=self._headers,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 401:
                raise PermissionError("Auth failed")
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"HTTP {resp.status}")
            data = await resp.json()
            if "errors" in data:
                errors = [e.get("message", "?") for e in data["errors"]]
                raise Exception(f"GraphQL error: {errors[0]}")
            return data.get("data", {})

    async def _graphql_request(self, query: str, variables: dict = None,
                               operation_name: str = None) -> dict:
        """Send GraphQL request with mirror fallback."""
        from urllib.parse import urljoin
        last_err = None
        tried_urls = []

        for mirror_url in self._resolve_mirror_list():
            url = mirror_url.rstrip("/") + "/_api/graphql"
            tried_urls.append(url)
            try:
                return await self._try_graphql(url, query, variables, operation_name)
            except PermissionError:
                # Auth failed - no point trying other mirrors
                raise
            except Exception as e:
                last_err = e
                continue

        raise Exception(
            f"All mirrors failed ({len(tried_urls)} tried). Last: {last_err}"
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._headers = {
                "x-access-token": self.config.access_token,
                "Content-Type": "application/json",
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

    # ── Auth / Balance ──────────────────────────────────────

    async def check_auth(self) -> bool:
        """Test if access token works (tries mirrors if enabled)."""
        try:
            data = await self._graphql_request("""
                query { user { id name } }
            """)
            return data.get("user") is not None
        except Exception:
            return False

    async def get_balance_simple(self) -> dict:
        """Get simplified balance (handles both dict & list formats)."""
        try:
            data = await self._graphql_request("""
                query UserBalances {
                    user {
                        balances {
                            available { amount currency }
                        }
                    }
                }
            """)
            user = data.get("user", {})
            balances = user.get("balances", {})

            # Stake API kadang return balances sebagai array, kadang sebagai dict
            if isinstance(balances, list):
                available_list = []
                for b in balances:
                    if isinstance(b, dict):
                        avail = b.get("available", [])
                        if isinstance(avail, list):
                            available_list.extend(avail)
            else:
                available_list = balances.get("available", [])

            if not isinstance(available_list, list):
                available_list = []

            result = {}
            for bal in available_list:
                currency = bal.get("currency", "btc").lower()
                result[currency] = float(bal.get("amount", 0))
            return result
        except Exception as e:
            return {"error": str(e)}

    async def get_balance_idr(self) -> str:
        """Get balance with IDR conversion."""
        try:
            bal = await self.get_balance_simple()
            if "error" in bal:
                return f"❌ {bal['error']}"

            rates = await self._fetch_crypto_rates()
            lines = []
            for currency, amount in bal.items():
                if amount <= 0:
                    continue
                curr_upper = currency.upper()
                rate = rates.get(currency, 0)
                if rate > 0:
                    lines.append(f"  {amount:.8f} {curr_upper}  ≈  Rp {amount * rate:,.0f}")
                else:
                    lines.append(f"  {amount:.8f} {curr_upper}")

            if not lines:
                return "  0 (kosong)"
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    async def _fetch_crypto_rates(self) -> dict:
        """Fetch crypto prices in IDR from CoinGecko."""
        try:
            session = await self._get_session()
            url = (
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=bitcoin,ethereum,tether,binancecoin,litecoin"
                "&vs_currencies=idr"
            )
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "btc": data.get("bitcoin", {}).get("idr", 0),
                        "eth": data.get("ethereum", {}).get("idr", 0),
                        "usdt": data.get("tether", {}).get("idr", 0),
                        "usdc": data.get("tether", {}).get("idr", 0),
                        "bnb": data.get("binancecoin", {}).get("idr", 0),
                        "ltc": data.get("litecoin", {}).get("idr", 0),
                    }
        except:
            pass
        return {}

    # ── Coin / Currency helpers ────────────────────────────

    CURRENCIES = [
        "btc", "eth", "usdt", "usdc", "ltc", "doge", "bch", "xrp",
        "trx", "ada", "dot", "sol", "matic", "avax", "link", "uni",
        "atom", "near", "ftm", "algo", "apt", "arb", "op", "sui",
        "inj", "sei", "tia", "aave", "crv", "mkr", "floki", "pepe",
        "shib", "wif", "bonk", "ens", "eos", "xlm", "zec", "dash",
        "etc", "waves", "icp", "fil", "vet", "rune", "dydx", "comp",
        "sushi", "axs", "sand", "mana", "chz", "enj", "gala", "ape",
        "lrc", "imx", "storj", "stx", "hbar", "flow", "ksm", "rose",
        "fet", "agix", "ocean", "bat", "grt", "ankr", "blur", "pyth",
        "ldo", "amp", "mina", "celo", "stark", "strk", "ondo", "io",
        "zk", "zro", "not", "dogs", "hmstr", "cat", "neiro", "goat",
        "act", "pnut", "mog", "popcat", "mew", "myro", "slerf", "sc",
        "poly", "zen", "egld", "kava", "osmo", "busd", "dai", "fdusd",
    ]

    @staticmethod
    def coin_to_stake_currency(coin: str) -> str:
        """Convert 'btc' → 'BTC' (Stake uses uppercase)."""
        return coin.upper()

    # ── Dice ────────────────────────────────────────────────

    async def place_dice_bet(self, amount: float, target: float, over: bool,
                              currency: str = "btc") -> dict:
        curr = self.coin_to_stake_currency(currency)
        query = """
        mutation DicePlay($amount: Float!, $target: Float!, $over: Boolean!, $currency: Currency!) {
            dicePlay(input: { amount: $amount, target: $target, over: $over, currency: $currency }) {
                id amount payout multiplier outcome currency
                user { balance }
            }
        }
        """
        try:
            data = await self._graphql_request(query, {
                "amount": amount, "target": target, "over": over, "currency": curr
            })
            r = data.get("dicePlay", {})
            return {
                "id": r.get("id", ""),
                "amount": float(r.get("amount", 0)),
                "payout": float(r.get("payout", 0)),
                "multiplier": float(r.get("multiplier", 0)),
                "outcome": r.get("outcome", ""),
                "won": r.get("outcome") == "win",
                "balance_after": r.get("user", {}).get("balance"),
                "currency": r.get("currency", currency),
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Limbo ───────────────────────────────────────────────

    async def place_limbo_bet(self, amount: float, target_multiplier: float,
                               currency: str = "btc") -> dict:
        curr = self.coin_to_stake_currency(currency)
        query = """
        mutation LimboPlay($amount: Float!, $targetMultiplier: Float!, $currency: Currency!) {
            limboPlay(input: { amount: $amount, targetMultiplier: $targetMultiplier, currency: $currency }) {
                id amount payout multiplier outcome
                crashMultiplier targetMultiplier currency
                user { balance }
            }
        }
        """
        try:
            data = await self._graphql_request(query, {
                "amount": amount, "targetMultiplier": target_multiplier, "currency": curr
            })
            r = data.get("limboPlay", {})
            return {
                "id": r.get("id", ""),
                "amount": float(r.get("amount", 0)),
                "payout": float(r.get("payout", 0)),
                "multiplier": float(r.get("multiplier", 0)),
                "outcome": r.get("outcome", ""),
                "won": r.get("outcome") == "win",
                "balance_after": r.get("user", {}).get("balance"),
                "crash_point": float(r.get("crashMultiplier", 0)),
                "target_multiplier": float(r.get("targetMultiplier", 0)),
                "currency": r.get("currency", currency),
            }
        except Exception as e:
            return {"error": str(e)}


async def test_auth(token: str) -> bool:
    """Quick test (default domain)."""
    return await test_auth_from_config(StakeConfig(access_token=token))


async def test_auth_from_config(cfg: StakeConfig) -> bool:
    """Test auth with custom config (supports mirror fallback)."""
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
║  1. Buka Stake.com (atau mirror) di Kiwi Browser         ║
║  2. Login ke akun kamu                                   ║
║  3. Tap 3 titik → Developer Tools                        ║
║  4. Tab Network → filter: graphql                        ║
║  5. Klik salah satu request /_api/graphql                ║
║  6. Cari header "x-access-token" → copy value-nya        ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    print(get_token_from_browser_instructions())
