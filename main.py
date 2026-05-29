#!/usr/bin/env python3
"""
StakeBot — Taraje 2.8.0 Compatible Betting Bot
🎲 Dice | 🚀 Limbo | 📜 LUA Scripts

Usage:
  python main.py              → Interactive menu
  python main.py auth         → Setup token (manual)
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

# ── UI shortcuts ──

def _c(tag: str, text="") -> str:
    colors = {"cyan": "36", "green": "32", "yellow": "33",
              "red": "31", "white": "97", "dim": "2", "bold": "1"}
    code = colors.get(tag, "0")
    return f"\033[{code}m{text}\033[0m"

def _banner():
    click.echo(f"\n{_c('bold')}  🎲 StakeBot — Taraje Compatible{_c('reset')}")
    click.echo(f"{_c('dim')}  Dice / Limbo / LUA Scripts{_c('reset')}\n")

def _pick(prompt: str, choices: list[str], default: int = 1) -> str:
    click.echo(_c("yellow", prompt))
    for i, ch in enumerate(choices, 1):
        m = _c("cyan", "▶") if i == default else " "
        click.echo(f"  {m} {_c('white', str(i))}. {ch}")
    val = click.prompt(f"  pilihan (1-{len(choices)})", type=int, default=default, show_default=False)
    return choices[min(max(val, 1), len(choices)) - 1]

# ── Shared ──

def _load_cfg() -> StakeConfig:
    return StakeConfig.load()

def _need_token(cfg: StakeConfig) -> bool:
    if not cfg.is_configured:
        click.echo(_c("red", "\n❌ Belum ada token!"))
        click.echo(f"  Jalankan: {_c('white', 'python main.py curl')}")
        click.echo(f"  Atau:     {_c('white', 'python main.py auth')}")
        return False
    return True

def _read_multiline(prompt: str = "  > ") -> str:
    """Read multiline input until double-enter (empty line)."""
    click.echo(_c("dim", "  (paste, lalu Enter 2x untuk selesai)"))
    lines = []
    while True:
        try:
            line = input(prompt)
            if line.strip() == "":
                if lines:
                    break
            else:
                lines.append(line.strip())
        except (EOFError, KeyboardInterrupt):
            break
    return "\n".join(lines)


# ═══════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════

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
    _banner()
    m = _pick("🌐 Pilih mirror:",
              ["auto (coba semua)", "stake.mba", "stake.com",
               "playstake.club", "custom (input sendiri)"], 1)

    if "auto" in m:
        url, mode = "https://stake.com", True
    elif "custom" in m:
        u = click.prompt("  URL mirror", default="stake.mba")
        url = f"https://{u}" if not u.startswith("http") else u
        mode = False
    else:
        url, mode = f"https://{m}", False

    click.echo(f"  → Mirror: {_c('green', url)}")

    click.echo(f"\n{_c('yellow', '🔑 Paste x-access-token:')}")
    click.echo(f"  {_c('dim', 'DevTools → Network → filter graphql → request headers')}")
    token = click.prompt("  Token", hide_input=True)

    StakeConfig(access_token=token, base_url=url, mirror_mode=mode).save()
    click.echo(_c("green", "\n  ✅ Config tersimpan!"))
    click.echo(f"  Coba: {_c('white', 'python main.py balance')}")


# ── curl ──

@cli.command()
def curl():
    """Setup dari cURL command — paling gampang!"""
    _banner()
    click.echo(_c("yellow", "📋 Copy as cURL dari browser:"))
    click.echo(textwrap.dedent(f"""
      {_c('dim', '1.')} Buka stake.mba di Kiwi → login
      {_c('dim', '2.')} DevTools → Network → filter: graphql
      {_c('dim', '3.')} Right-click request /_api/graphql
      {_c('dim', '4.')} Copy → Copy as cURL
    """))

    curl_text = _read_multiline()

    if not curl_text.strip():
        click.echo(_c("red", "  ❌ Tidak ada input!"))
        return

    click.echo(f"\n  {_c('dim', 'Parsing...')}")

    p = parse_curl(curl_text)
    token = p.get("access_token", "")
    cookie = p.get("session_cookie", "")
    url = p.get("url", "https://stake.com")

    if not token:
        click.echo(_c("red", f"\n  ❌ Token tidak ditemukan!"))
        click.echo(f"  Input: {curl_text[:100]}")
        click.echo(f"\n  {_c('yellow', 'Tips:')}")
        click.echo(f"  - Pastikan copy dari request {_c('white', '/_api/graphql')}")
        click.echo(f"  - Bukan dari request lain (websocket, static, dll)")
        click.echo(f"  - Alternatif: {_c('white', 'python main.py auth')} input manual")
        return

    # Detect mirror from URL
    mirror_url = "https://stake.com"
    for m in MIRRORS:
        if m in url:
            mirror_url = m
            break

    StakeConfig(
        access_token=token, session_cookie=cookie,
        base_url=mirror_url, mirror_mode=True,
    ).save()

    click.echo(_c("green", f"\n  ✅ Config tersimpan!"))
    click.echo(f"     Token: {token[:12]}...{token[-6:]}")
    if cookie:
        click.echo(f"     Cookie: {len(cookie)} chars")
    click.echo(f"     Mirror: {mirror_url}")
    click.echo(f"\n  Coba: {_c('white', 'python main.py balance')}")


# ── balance ──

@cli.command()
def balance():
    """💰 Cek saldo."""
    _banner()
    cfg = _load_cfg()
    if not _need_token(cfg):
        return

    async def _b():
        try:
            async with StakeClient(cfg) as client:
                u = await client.get_user()
                click.echo(_c("green", f"  👤 {u['name']}"))
                click.echo(f"  {'─'*30}")
                bal = client.balance
                if not bal:
                    click.echo(_c("dim", "  (saldo kosong)"))
                else:
                    for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                        if a > 0:
                            click.echo(f"  {c.upper():>6}  {a:.8f}")
        except AuthError:
            click.echo(_c("red", "\n❌ Token expired / invalid!"))
            click.echo(f"  Jalankan: {_c('white', 'python main.py curl')}")
        except ConnectionError as e:
            click.echo(_c("red", f"\n❌ Gagal connect"))
            click.echo(f"  Coba: {_c('white', 'python main.py test')}")
    asyncio.run(_b())


# ── test ──

@cli.command()
def test():
    """🔍 Diagnostik — cek semua mirror."""
    _banner()
    cfg = _load_cfg()
    if not _need_token(cfg):
        return

    async def _t():
        click.echo(_c("yellow", "🔍 Mencoba semua mirror...\n"))
        async with StakeClient(cfg) as client:
            for url in MIRRORS:
                try:
                    click.echo(f"  {_c('dim', url + ':')} ", nl=False)
                    r = await client._try_url(url, "{ user { id name } }", {})
                    if r:
                        click.echo(_c("green", "✅ OK"))
                        click.echo(f"\n  {_c('green', 'Mirror berfungsi!')} Update config:")
                        click.echo(f"  {_c('white', 'python main.py auth')}")
                        return
                    else:
                        click.echo(_c("red", "❌ blocked"))
                except Exception as e:
                    click.echo(_c("red", f"❌ {str(e)[:40]}"))
            click.echo(f"\n{_c('red', '❌ Semua mirror diblokir! Coba VPN.')}")
    asyncio.run(_t())


# ── run (interactive) ──

@cli.command()
def run():
    """🎮 Interactive betting session."""
    _banner()
    cfg = _load_cfg()
    if not _need_token(cfg):
        return

    # 1. Game
    game = _pick("🎮 Game:", ["Dice 🎲", "Limbo 🚀"], 1)
    game_type = "limbo" if "Limbo" in game else "dice"

    # 2. Coin
    coin = _pick("🪙 Coin:", ["USDT", "LTC", "BTC", "ETH", "SOL", "DOGE", "TRX", "BNB", "Lainnya"], 1)
    if coin == "Lainnya":
        coin = click.prompt("  Kode coin", default="DOT").upper()

    # 3. Base bet
    defaults = {"BTC": 1e-8, "ETH": 1e-5, "USDT": 0.01, "LTC": 0.001, "SOL": 0.001, "DOGE": 1.0, "TRX": 1.0}
    bb = click.prompt(f"  💰 Base bet ({coin})", type=float, default=defaults.get(coin, 0.01))

    # 4. Target
    if game_type == "dice":
        target = click.prompt("  🎯 Chance (%)", type=float, default=49.5)
        cond = _pick("  📈 Arah:", ["Above (roll > target)", "Below (roll < target)"], 1)
        condition = "above" if "Above" in cond else "below"
    else:
        target = click.prompt("  🎯 Multiplier (x)", type=float, default=2.0)
        condition = "above"

    # 5. Script
    lua_engine = None
    if click.confirm("📜 Pakai LUA script?", default=True):
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem.replace("_", " ").title() for s in scripts]
            chosen = _pick("  Strategi:", snames, 1)
            idx = snames.index(chosen)
            try:
                lua_engine = LuaScriptEngine(scripts[idx].read_text())
                click.echo(f"  {_c('green', '📜 ' + scripts[idx].name)}")
            except Exception as e:
                click.echo(_c("red", f"  ❌ LUA error: {e}"))
                return

    # 6. Stop conditions
    max_bets, stop_profit, stop_loss = 0, 0.0, 0.0
    if click.confirm("⏹️  Stop conditions?", default=False):
        max_bets = click.prompt("  Max bets (0=∞)", type=int, default=0)
        stop_profit = click.prompt("  Stop profit (0=∞)", type=float, default=0.0)
        stop_loss = click.prompt("  Stop loss (0=∞)", type=float, default=0.0)

    # 7. Confirm
    click.echo(f"\n{_c('cyan', '  Ringkasan:')}")
    click.echo(f"  Game: {game} | Coin: {coin} | Bet: {bb}")
    click.echo(f"  {'Chance: '+str(target)+'% | '+condition if game_type=='dice' else 'Multiplier: '+str(target)+'x'}")
    if not click.confirm(f"\n  {_c('yellow', '🔥 Mulai?')}", default=True):
        return

    bc = BetConfig(game=game_type, coin=coin.lower(), base_bet=bb,
                   target=target, condition=condition,
                   max_bets=max_bets, stop_profit=stop_profit, stop_loss=stop_loss)
    asyncio.run(_run_session(cfg, bc, lua_engine))


async def _run_session(cfg: StakeConfig, bc: BetConfig, lua=None):
    """Betting session with live stats."""
    async with StakeClient(cfg) as client:
        try:
            user = await client.get_user()
        except AuthError:
            click.echo(_c("red", "\n❌ Token expired!"))
            click.echo(f"  Jalankan: {_c('white', 'python main.py curl')}")
            return
        except ConnectionError:
            click.echo(_c("red", "\n❌ Gagal koneksi!"))
            click.echo(f"  Coba: {_c('white', 'python main.py test')}")
            return

        bal = client.balance.get(bc.coin, 0)
        if bal < bc.base_bet:
            click.echo(_c("red", f"\n❌ Saldo {bc.coin.upper()} tidak cukup!"))
            click.echo(f"  Saldo: {bal:.8f}  |  Bet: {bc.base_bet:.8f}")
            return

        click.echo(f"\n{_c('cyan', '▶️  ' + '='*32)}")
        click.echo(f"  {_c('green', user['name'])}  {bc.coin.upper()}  Bet={bc.base_bet}")
        click.echo(f"  {_c('dim', 'Ctrl+C to stop')}")
        click.echo(f"{_c('cyan', '  ' + '='*32)}\n")

        engine = BettingEngine(client=client, config=bc, lua_engine=lua)
        try:
            stats = await engine.run()
        except KeyboardInterrupt:
            engine.stop()
            await asyncio.sleep(0.5)
            stats = engine.stats
            click.echo()

        click.echo(f"\n{_c('cyan', '  ' + '='*32)}")
        click.echo(f"  {_c('white', 'SELESAI')}")
        click.echo(f"  Bets: {stats.bets}  |  ✅{stats.wins}  ❌{stats.losses}")
        color = "green" if stats.profit >= 0 else "red"
        click.echo(f"  Profit: {_c(color, f'{stats.profit:+.8f} {bc.coin.upper()}')}")
        click.echo(f"  Streak: {stats.best_streak}↗ / {stats.worst_streak}↘")
        click.echo(f"{_c('cyan', '  ' + '='*32)}")


def main():
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "run"]
    cli()


if __name__ == "__main__":
    main()
