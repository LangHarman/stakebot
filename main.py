#!/usr/bin/env python3
"""
StakeBot — Taraje 2.8.0 Compatible Betting Bot
🎲 Dice | 🚀 Limbo | 📜 LUA Scripts

Usage:
  python main.py              → Interactive menu
  python main.py auth         → Setup token
  python main.py curl         → Setup dari cURL (termudah)
  python main.py balance      → Cek saldo
  python main.py test         → Diagnostik koneksi
"""
from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import click

from core.client import (
    StakeConfig, StakeClient, AuthError, ConnectionError,
    parse_curl, MIRRORS,
)
from core.engine import BettingEngine, BetConfig, BetStats
from core.script_engine import LuaScriptEngine

SCRIPT_DIR = Path(__file__).parent / "scripts"

# ── UI Helpers ──

C = {
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "white": "\033[97m", "bold": "\033[1m",
    "dim": "\033[2m", "reset": "\033[0m",
}

def c(tag: str, text="") -> str:
    return f"{C.get(tag, '')}{text}{C['reset']}"

def banner():
    click.echo()
    click.echo(c("bold") + "  🎲 StakeBot — Taraje Compatible" + c("reset"))
    click.echo(c("dim") + "  Dice / Limbo / LUA Scripts" + c("reset"))
    click.echo()

def pick(prompt: str, choices: list[str], default: int = 1) -> str:
    """Show numbered menu, return selected string."""
    click.echo(c("yellow", prompt))
    for i, ch in enumerate(choices, 1):
        marker = c("cyan", "▶") if i == default else " "
        click.echo(f"  {marker} {c('white', str(i))}. {ch}")
    try:
        val = click.prompt(f"  pilihan (1-{len(choices)})", type=int,
                           default=default, show_default=False)
        idx = min(max(val, 1), len(choices)) - 1
    except click.Abort:
        idx = default - 1
    return choices[idx]


def fmt_coin(bal: float, code: str) -> str:
    """Format balance with appropriate decimals."""
    if bal < 0.0001:
        return f"{bal:.8f} {code.upper()}"
    elif bal < 1:
        return f"{bal:.6f} {code.upper()}"
    return f"{bal:.4f} {code.upper()}"

# ── Shared helpers ──

def load_config() -> StakeConfig:
    return StakeConfig.load()

def check_config(cfg: StakeConfig) -> bool:
    if not cfg.is_configured:
        click.echo(c("red", "\n❌ Belum ada token!"))
        click.echo(f"  Jalankan: {c('white', 'python main.py auth')}")
        click.echo(f"  Atau:     {c('white', 'python main.py curl')}  (copy dari browser)")
        return False
    return True


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """StakeBot — Taraje Compatible 🎲"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


# ── auth ──

@cli.command()
def auth():
    """Setup: pilih mirror → paste token → simpan."""
    banner()
    m = pick(c("yellow", "🌐 Pilih mirror:"),
             ["auto (coba semua)", "stake.mba", "stake.com",
              "playstake.club", "custom (input sendiri)"], default=1)

    if "auto" in m:
        mirror_url, mirror_mode = "https://stake.com", True
    elif "custom" in m:
        url = click.prompt("  URL mirror", default="stake.mba")
        mirror_url = f"https://{url}" if not url.startswith("http") else url
        mirror_mode = False
    else:
        mirror_url = f"https://{m}"
        mirror_mode = False

    click.echo(f"  → Mirror: {c('green', mirror_url)}")

    click.echo(f"\n{c('yellow', '🔑 Paste x-access-token:')}")
    click.echo(f"  {c('dim', '(DevTools → Network → filter graphql → request headers)')}")
    token = click.prompt("  Token", hide_input=True)

    cfg = StakeConfig(
        access_token=token,
        base_url=mirror_url,
        mirror_mode=mirror_mode,
    )
    cfg.save()
    click.echo(c("green", "\n  ✅ Config tersimpan!"))
    click.echo(f"  Coba: {c('white', 'python main.py balance')}")


@cli.command()
def curl():
    """Setup dari cURL command — paling gampang!"""
    banner()
    click.echo(c("yellow", "📋 Copy as cURL dari browser:"))
    click.echo(textwrap.dedent(f"""
      {c('dim', '1.')} Buka stake.mba di Kiwi → login
      {c('dim', '2.')} DevTools → Network → filter: graphql
      {c('dim', '3.')} Right-click request /_api/graphql
      {c('dim', '4.')} Copy → Copy as cURL
      {c('dim', '5.')} Paste di sini:
    """))
    curl_text = click.prompt("  cURL")

    p = parse_curl(curl_text)
    token = p.get("access_token", "")
    cookie = p.get("session_cookie", "")
    url = p.get("url", "https://stake.com")

    if not token:
        click.echo(c("red", "\n  ❌ Token tidak ditemukan!"))
        click.echo("     Pastikan copy dari request /_api/graphql.")
        return

    # Extract mirror from URL
    mirror_url = "https://stake.com"
    for m in MIRRORS:
        if m in url:
            mirror_url = m
            break

    cfg = StakeConfig(
        access_token=token,
        session_cookie=cookie,
        base_url=mirror_url,
        mirror_mode=True,
    )
    cfg.save()

    click.echo(c("green", f"\n  ✅ Config tersimpan!"))
    click.echo(f"     Token: {token[:12]}...{token[-6:]}")
    if cookie:
        click.echo(f"     Cookie: {len(cookie)} chars")
    click.echo(f"     Mirror: {mirror_url}")
    click.echo(f"\n  Coba: {c('white', 'python main.py balance')}")


# ── balance ──

@cli.command()
def balance():
    """💰 Cek saldo."""
    banner()
    cfg = load_config()
    if not check_config(cfg):
        return

    async def _run():
        try:
            async with StakeClient(cfg) as client:
                u = await client.get_user()
                bal = client.balance
                click.echo(c("green", f"  👤 {u['name']}"))
                click.echo(f"  {'─'*30}")
                if not bal:
                    click.echo(c("dim", "  (saldo kosong)"))
                else:
                    for coin_code, amount in sorted(bal.items(),
                                                    key=lambda x: -x[1]):
                        if amount > 0:
                            click.echo(f"  {fmt_coin(amount, coin_code)}")
        except AuthError:
            click.echo(c("red", "\n❌ Token expired / invalid!"))
            click.echo(f"  Jalankan: {c('white', 'python main.py auth')}")
        except ConnectionError as e:
            click.echo(c("red", f"\n❌ Gagal connect: {e}"))
            click.echo(f"  Coba: {c('white', 'python main.py test')}")
    asyncio.run(_run())


# ── test ──

@cli.command()
def test():
    """🔍 Diagnostik — cek semua mirror."""
    banner()
    cfg = load_config()
    if not check_config(cfg):
        return

    async def _run():
        click.echo(c("yellow", "🔍 Mencoba semua mirror...\n"))
        async with StakeClient(cfg) as client:
            for url in MIRRORS:
                try:
                    click.echo(f"  {c('dim', url+':')} ", nl=False)
                    result = await client._try_url(url, "query { user { name } }", {})
                    if result:
                        click.echo(c("green", "✅ OK"))
                        click.echo(f"\n  {c('green', 'Mirror berfungsi!')} Simpan config:")
                        click.echo(f"  {c('white', 'python main.py auth')}")
                        return
                    else:
                        click.echo(c("red", "❌ blocked"))
                except Exception as e:
                    click.echo(c("red", f"❌ {str(e)[:40]}"))
                    break

            click.echo(f"\n{c('red', '❌ Semua mirror diblokir!')}")
            click.echo(f"  Coba VPN atau proxy.")
    asyncio.run(_run())


# ── run (interactive) ──

@cli.command()
def run():
    """🎮 Interactive betting session."""
    banner()
    cfg = load_config()
    if not check_config(cfg):
        return

    # 1. Game
    game = pick("🎮 Game:", ["Dice 🎲", "Limbo 🚀"])
    game_type = "limbo" if "Limbo" in game else "dice"

    # 2. Coin
    coins = ["USDT", "LTC", "BTC", "ETH", "SOL", "DOGE", "TRX", "BNB", "Lainnya"]
    coin = pick("🪙 Coin:", coins, default=1)
    if coin == "Lainnya":
        coin = click.prompt("  Kode coin", default="DOT").upper()

    # 3. Base bet
    defaults = {"BTC": 0.00000001, "ETH": 0.00001, "USDT": 0.01,
                "LTC": 0.001, "SOL": 0.001, "DOGE": 1.0, "TRX": 1.0}
    default_bet = defaults.get(coin, 0.01)
    base_bet = click.prompt(
        f"  💰 Base bet ({coin})", type=float, default=default_bet)

    # 4. Target
    if game_type == "dice":
        target = click.prompt("  🎯 Chance (%)", type=float, default=49.5)
        cond = pick("  📈 Arah:", ["Above (roll > target)", "Below (roll < target)"])
        condition = "above" if "Above" in cond else "below"
    else:
        target = click.prompt("  🎯 Multiplier (x)", type=float, default=2.0)
        condition = "above"

    # 5. Script
    use_script = click.confirm("📜 Pakai LUA script?", default=True)
    lua_engine = None
    if use_script:
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem.replace("_", " ").title() for s in scripts]
            chosen = pick("  Strategi:", snames, default=1)
            idx = snames.index(chosen)
            path = scripts[idx]
            try:
                lua_engine = LuaScriptEngine(path.read_text())
                click.echo(f"  {c('green', '📜 ' + path.name)}")
            except Exception as e:
                click.echo(c("red", f"  ❌ LUA error: {e}"))
                return
        else:
            click.echo(c("dim", "  (tidak ada scripts/*.lua)"))

    # 6. Stop conditions
    max_bets = 0
    stop_profit = 0.0
    stop_loss = 0.0
    if click.confirm("⏹️  Stop conditions?", default=False):
        max_bets = click.prompt("  Max bets (0=∞)", type=int, default=0)
        stop_profit = click.prompt("  Stop profit (0=∞)", type=float, default=0.0)
        stop_loss = click.prompt("  Stop loss (0=∞)", type=float, default=0.0)

    # 7. Confirm & start
    click.echo(f"\n{c('cyan', '  Ringkasan:')}")
    click.echo(f"  Game: {game} | Coin: {coin} | Bet: {base_bet}")
    if game_type == "dice":
        click.echo(f"  Chance: {target}% | {condition}")
    else:
        click.echo(f"  Multiplier: {target}x")

    if not click.confirm(f"\n  {c('yellow', '🔥 Mulai?')}", default=True):
        click.echo("  Batal.")
        return

    bc = BetConfig(
        game=game_type, coin=coin.lower(), base_bet=base_bet,
        target=target, condition=condition or "above",
        max_bets=max_bets, stop_profit=stop_profit, stop_loss=stop_loss,
    )

    asyncio.run(_run_session(cfg, bc, lua_engine))


async def _run_session(cfg: StakeConfig, bc: BetConfig, lua=None):
    """Run a betting session with live display."""
    async with StakeClient(cfg) as client:
        # Verify auth
        try:
            user = await client.get_user()
        except AuthError:
            click.echo(c("red", "\n❌ Token expired!"))
            click.echo(f"  Jalankan: {c('white', 'python main.py curl')}")
            return
        except ConnectionError:
            click.echo(c("red", "\n❌ Gagal koneksi!"))
            click.echo(f"  Coba: {c('white', 'python main.py test')}")
            return

        bal = client.balance.get(bc.coin, 0)
        if bal < bc.base_bet:
            click.echo(c("red", f"\n❌ Saldo {bc.coin.upper()} tidak cukup!"))
            click.echo(f"  Saldo: {fmt_coin(bal, bc.coin)}")
            click.echo(f"  Bet:   {fmt_coin(bc.base_bet, bc.coin)}")
            return

        click.echo(f"\n{c('cyan', '▶️  ' + '='*32)}")
        click.echo(f"  {c('green', user['name'])}  {bc.coin.upper()}  Bet={bc.base_bet}")
        click.echo(f"  {c('dim', 'Ctrl+C to stop')}")
        click.echo(f"{c('cyan', '  ' + '='*32)}\n")

        engine = BettingEngine(
            client=client, config=bc, lua_engine=lua,
        )

        try:
            stats = await engine.run()
        except KeyboardInterrupt:
            engine.stop()
            stats = engine.stats
            click.echo()

        # Summary
        click.echo(f"\n{c('cyan', '  ' + '='*32)}")
        click.echo(f"  {c('white', 'SELESAI')}")
        click.echo(f"  Bets: {stats.bets}  |  ✅{stats.wins}  ❌{stats.losses}")
        click.echo(f"  Profit: {c('green' if stats.profit >= 0 else 'red', f'{stats.profit:+.8f} {bc.coin.upper()}')}")
        click.echo(f"  Streak: {stats.best_streak}↗ / {stats.worst_streak}↘")
        click.echo(f"{c('cyan', '  ' + '='*32)}")


# ── Entry ──

def main():
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "run"]
    cli()


if __name__ == "__main__":
    main()
