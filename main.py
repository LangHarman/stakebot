#!/usr/bin/env python3
"""
StakeBot CLI — Professional Taraje-Compatible Betting Bot
🎲 Dice | 🚀 Limbo | 📜 LUA Scripts

Usage:
  python main.py              → Interactive menu
  python main.py auth         → Setup token (manual paste)
  python main.py curl         → Setup dari cURL (paling gampang)
  python main.py balance      → Cek saldo
  python main.py test         → Diagnostik koneksi
  python main.py history      → Riwayat sesi
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import textwrap
from datetime import datetime
from pathlib import Path

import click

from core.client import (
    StakeConfig, StakeClient, AuthError, ConnectionError,
    parse_curl, MIRRORS,
)
from core.engine import BettingEngine, BetConfig
from core.script_engine import LuaScriptEngine
from core.logger import SessionLogger, list_sessions, read_summary

SCRIPT_DIR = Path(__file__).parent / "scripts"
VERSION = "2.8.1"

# ── UI Utilities ──

CSI = "\033["

def _c(code: str, text="") -> str:
    """ANSI color wrapper."""
    colors = {
        "cyan": "36", "green": "32", "yellow": "33",
        "red": "31", "white": "97", "magenta": "35",
        "dim": "2", "bold": "1", "reset": "0",
    }
    c_str = colors.get(code, "0")
    return f"{CSI}{c_str}m{text}{CSI}0m"

def _cls():
    """Clear screen (Termux/Linux compatible)."""
    os.system("clear 2>/dev/null || printf '\\033c'")

def _banner():
    """Simple header for auth/balance/test commands."""
    click.echo(f"\n{_c('bold')}  🎲 StakeBot v{VERSION}{_c('reset')}")
    click.echo(f"{_c('dim')}  Dice / Limbo / LUA Scripts{_c('reset')}\n")

def _pick(prompt: str, choices: list[str], default: int = 1) -> str:
    """Numbered menu picker."""
    click.echo(_c("yellow", prompt))
    for i, ch in enumerate(choices, 1):
        m = _c("cyan", "▶") if i == default else " "
        click.echo(f"  {m} {_c('white', str(i))}. {ch}")
    val = click.prompt(f"  pilihan (1-{len(choices)})", type=int,
                       default=default, show_default=False)
    return choices[min(max(val, 1), len(choices)) - 1]

def _read_multiline(prompt: str = "  > ") -> str:
    """Read multiline until empty line (double-enter)."""
    click.echo(_c("dim", "  (paste, lalu Enter kosong untuk selesai)"))
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


# ═════════════════════════════════════════════
#  SPLASH SCREEN
# ═════════════════════════════════════════════

SPLASH = """{c}
╔══════════════════════════════════════════╗
║                                          ║
║     {y}▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄{c}     ║
║     {y}██  BATAVIAN JAKER  ██{c}     ║
║     {w}▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀{c}     ║
║                                          ║
║     {m}Winner know when to stop!{c}           ║
║                                          ║
║     {g}Stake Bot v{VERSION}{c}                       ║
║     {d}Made by Melky & Batavian Jaker{c}     ║
║                                          ║
║     {d}2026{c}                                 ║
║                                          ║
╚══════════════════════════════════════════╝
   Loading...{R}
"""


def _splash():
    """Display splash screen for 2 seconds."""
    _cls()
    txt = (SPLASH
           .replace("{c}", _c("cyan"))
           .replace("{y}", _c("yellow"))
           .replace("{w}", _c("white"))
           .replace("{m}", _c("magenta"))
           .replace("{g}", _c("green"))
           .replace("{d}", _c("dim"))
           .replace("{R}", _c("reset"))
           .replace("{VERSION}", VERSION))
    click.echo(txt, nl=False)
    time.sleep(2)


# ═════════════════════════════════════════════
#  LIVE DISPLAY (Taraje-style real-time stats)
# ═════════════════════════════════════════════

class LiveDisplay:
    """Real-time Taraje-style live betting display.

    Shows a persistent header block updated each bet,
    plus a scrolling last-result line.
    """

    def __init__(self, game: str, coin: str, name: str):
        self.game = game
        self.coin = coin
        self.name = name
        self._last_bet_lines = 0
        self._header_printed = False

    def init(self):
        """Print initial header frame."""
        _cls()
        game_icon = "🚀" if self.game == "limbo" else "🎲"
        game_name = "LIMBO" if self.game == "limbo" else "DICE"

        lines = [
            f"{_c('cyan')}╔══════════════════════════════════════════╗{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('yellow')}STAKEBOT LIVE{_c('reset')} — {_c('bold')}{game_icon} {game_name}{_c('reset')}" + " " * 25 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╠══════════════════════════════════════════╣{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Player:{_c('reset')} {_c('green')}{self.name}{_c('reset')}" + " " * 26 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Coin:{_c('reset')}   {_c('white')}{self.coin.upper()}{_c('reset')}" + " " * 28 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╠══════════════════════════════════════════╣{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Starting...{_c('reset')}" + " " * 30 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╚══════════════════════════════════════════╝{_c('reset')}",
        ]
        click.echo("\n".join(lines))
        self._header_printed = True
        self._last_bet_lines = 8  # total header lines

    def update(self, bet_id: int, won: bool, streak: int, profit: float,
               balance: float, bet_amount: float, winrate: float,
               last_result: str, payout: float):
        """Update the live display with new bet result."""
        icon = f"{_c('green')}✅{_c('reset')}" if won else f"{_c('red')}❌{_c('reset')}"
        profit_color = "green" if profit >= 0 else "red"
        streak_sign = "+" if streak >= 0 else ""
        stre = f"{_c('red')}{streak}{_c('reset')}" if streak < 0 else f"{_c('green')}+{streak}{_c('reset')}"

        # Build header
        lines = [
            f"{_c('cyan')}╔══════════════════════════════════════════╗{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}#{bet_id}{_c('reset')} {icon}  {_c('dim')}S:{_c('reset')}{stre}  {_c('dim')}P:{_c('reset')}{_c(profit_color, f'{profit:+.8f}')}  {_c('dim')}WR:{_c('reset')}{winrate:.1f}%  {' '*10}{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Bet:{_c('reset')} {bet_amount:.8f}  {_c('dim')}Bal:{_c('reset')} {balance:.8f} {self.coin.upper()}{' '*11}{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╠══════════════════════════════════════════╣{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {last_result}{' '*(42 - len(last_result))}{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╚══════════════════════════════════════════╝{_c('reset')}",
        ]

        # Move cursor up and redraw
        if self._last_bet_lines > 0:
            click.echo(f"{CSI}{self._last_bet_lines}A", nl=False)
        click.echo("\n".join(lines))
        self._last_bet_lines = 6


# ═════════════════════════════════════════════
#  CUMULATIVE SUMMARY
# ═════════════════════════════════════════════

def _show_summary(stats, bc: BetConfig, logger: SessionLogger,
                  stop_reason: str = ""):
    """Display cumulative session stats after stopping."""
    _cls()

    profit_color = "green" if stats.profit >= 0 else "red"
    now = datetime.now().strftime("%H:%M:%S")

    lines = [
        "",
        f"{_c('cyan')}╔══════════════════════════════════════════════╗{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}          {_c('yellow')}SESSION SUMMARY{_c('reset')}                    {_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}╠══════════════════════════════════════════════╣{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Game:{_c('reset')}  {'🚀 LIMBO' if bc.game == 'limbo' else '🎲 DICE'}{' '*27}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Coin:{_c('reset')}  {bc.coin.upper()}{' '*33}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Base Bet:{_c('reset')} {bc.base_bet:.8f}{' '*22}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}╠══════════════════════════════════════════════╣{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Total Bets:{_c('reset')} {stats.bets}{' '*26}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('green')}✅ Wins:{_c('reset')}   {stats.wins}{' '*26}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('red')}❌ Losses:{_c('reset')}  {stats.losses}{' '*26}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Winrate:{_c('reset')} {stats.winrate:.1f}%{' '*25}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Profit:{_c('reset')} {_c(profit_color, f'{stats.profit:+.8f} {bc.coin.upper()}')}{' '*20}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Best Streak:{_c('reset')}  +{stats.best_streak}{' '*22}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Worst Streak:{_c('reset')} {stats.worst_streak}{' '*22}{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Biggest Bet:{_c('reset')} {stats.biggest_bet:.8f}{' '*21}{_c('cyan')}║{_c('reset')}",
    ]

    if stop_reason:
        lines.append(
            f"{_c('cyan')}╠══════════════════════════════════════════════╣{_c('reset')}"
        )
        lines.append(
            f"{_c('cyan')}║{_c('reset')}  {_c('red')}STOP: {stop_reason}{' '*(36 - len(stop_reason))}{_c('cyan')}║{_c('reset')}"
        )

    lines += [
        f"{_c('cyan')}╚══════════════════════════════════════════════╝{_c('reset')}",
        "",
        f"  {_c('dim')}Session saved: {logger.session_id}{_c('reset')}",
        f"  {_c('dim')}Log: {logger.path}{_c('reset')}",
        "",
    ]

    click.echo("\n".join(lines))


# ── Shared helpers ──

def _load_cfg() -> StakeConfig:
    return StakeConfig.load()

def _need_token(cfg: StakeConfig) -> bool:
    if not cfg.is_configured:
        click.echo(_c("red", "\n❌ Belum ada token!"))
        click.echo(f"  Jalankan: {_c('white', 'python main.py curl')}")
        return False
    return True


# ═════════════════════════════════════════════
#  CLI GROUP
# ═════════════════════════════════════════════

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """StakeBot v{VERSION} — Taraje Compatible 🎲"""
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


# ── auth ──

@cli.command()
def auth():
    """🔑 Setup: pilih mirror → paste token → simpan."""
    _cls()
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
    click.echo(_c("green", "\n✅ Config tersimpan!"))
    click.echo(f"Coba: {_c('white', 'python main.py balance')}")


# ── curl ──

@cli.command()
def curl():
    """🔗 Setup dari cURL — termudah!"""
    _cls()
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
        click.echo(_c("red", "❌ Tidak ada input!"))
        return

    p = parse_curl(curl_text)
    token = p.get("access_token", "")
    if not token:
        click.echo(_c("red", f"\n❌ Token tidak ditemukan!"))
        click.echo(f"Input: {curl_text[:100]}")
        click.echo(f"\n{_c('yellow', 'Tips:')} Pastikan copy dari /_api/graphql")
        return

    cookie = p.get("session_cookie", "")
    url = p.get("url", "https://stake.com")
    mirror_url = "https://stake.com"
    for m in MIRRORS:
        if m in url:
            mirror_url = m
            break

    StakeConfig(access_token=token, session_cookie=cookie,
                base_url=mirror_url, mirror_mode=True).save()
    click.echo(_c("green", f"\n✅ Config tersimpan!"))
    click.echo(f"   Token: {token[:12]}...{token[-6:]}")
    click.echo(f"Coba: {_c('white', 'python main.py balance')}")


# ── balance ──

@cli.command()
def balance():
    """💰 Cek saldo."""
    _cls()
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
            click.echo(_c("red", "\n❌ Token expired!"))
        except ConnectionError:
            click.echo(_c("red", "\n❌ Gagal connect!"))
    asyncio.run(_b())


# ── test ──

@cli.command()
def test():
    """🔍 Diagnostik koneksi."""
    _cls()
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
                        click.echo(f"\n{_c('green', 'Mirror berfungsi!')}")
                        return
                    else:
                        click.echo(_c("red", "❌ blocked"))
                except Exception as e:
                    click.echo(_c("red", f"❌ {str(e)[:40]}"))
            click.echo(f"\n{_c('red', '❌ Semua mirror diblokir! Coba VPN.')}")
    asyncio.run(_t())


# ── history ──

@cli.command()
def history():
    """📋 Riwayat sesi sebelumnya."""
    _cls()
    _banner()
    sessions = list_sessions(15)
    if not sessions:
        click.echo(_c("dim", "  Belum ada riwayat sesi."))
        return

    click.echo(f"{_c('yellow', '📋 Sesi terakhir:')}\n")
    for i, s in enumerate(sessions[:10], 1):
        try:
            sm = read_summary(s)
            profit = sm.get("profit", 0)
            p_str = _c("green", f"+{profit:.6f}") if profit >= 0 else _c("red", f"{profit:.6f}")
            wl = f"✅{sm.get('wins',0)}/❌{sm.get('losses',0)}"
            ts = s.stem.replace("session_", "")
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
            game = sm.get("game", "?").upper()
            coin = sm.get("coin", "?").upper()
            click.echo(f"  {i:>2}. {_c('dim', date)}  {game:5} {coin:6}  {wl}  {p_str}")
        except Exception:
            click.echo(f"  {i:>2}. {_c('dim', s.stem)} (error reading)")


# ═════════════════════════════════════════════
#  MAIN RUN — Professional Interactive Flow
# ═════════════════════════════════════════════

@cli.command()
def run():
    """🎮 Professional interactive betting session."""

    # ── STEP 0: Splash Screen ──
    _splash()
    _cls()

    cfg = _load_cfg()
    if not _need_token(cfg):
        return

    # Verify auth
    async def _verify():
        async with StakeClient(cfg) as client:
            return await client.get_user()
    try:
        user = asyncio.run(_verify())
    except AuthError:
        click.echo(_c("red", "\n❌ Token expired!"))
        click.echo(f"Jalankan: {_c('white', 'python main.py curl')}")
        return
    except ConnectionError:
        click.echo(_c("red", "\n❌ Gagal koneksi!"))
        click.echo(f"Coba: {_c('white', 'python main.py test')}")
        return

    player_name = user.get("name", "Player")

    # ── STEP 1: Pilih Game (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}PILIH GAME{_c('reset')}                    {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")
    game = _pick("", ["🎲 Dice", "🚀 Limbo"], 1)
    game_type = "limbo" if "Limbo" in game else "dice"

    # ── STEP 2: Pilih Coin (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}PILIH COIN{_c('reset')}                    {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")
    coin = _pick("", ["USDT", "LTC", "BTC", "ETH", "SOL", "DOGE", "TRX", "BNB", "Lainnya"], 1)
    if coin == "Lainnya":
        coin = click.prompt("  Kode coin", default="DOT").upper()

    # ── STEP 3: Base Bet (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}BASE BET ({coin}){_c('reset')}               {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")
    defaults = {"BTC": 1e-8, "ETH": 1e-5, "USDT": 0.01, "LTC": 0.001, "SOL": 0.001, "DOGE": 1.0, "TRX": 1.0}
    bb = click.prompt(f"  💰 Amount", type=float, default=defaults.get(coin, 0.01))

    # ── STEP 4: Target (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}TARGET{_c('reset')}                       {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")
    if game_type == "dice":
        target = click.prompt("  🎯 Chance (%)", type=float, default=49.5)
        cond = _pick("  📈 Roll condition:", ["Above (roll > target)", "Below (roll < target)"], 1)
        condition = "above" if "Above" in cond else "below"
    else:
        target = click.prompt("  🎯 Multiplier (x)", type=float, default=2.0)
        condition = "above"

    # ── STEP 5: Script (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}STRATEGI{_c('reset')}                     {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")

    lua_engine = None
    script_name = "manual"
    if click.confirm("📜 Gunakan LUA script?", default=True):
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem.replace("_", " ").title() for s in scripts]
            chosen = _pick("", snames, 1)
            idx = snames.index(chosen)
            script_name = scripts[idx].stem
            try:
                lua_engine = LuaScriptEngine(scripts[idx].read_text())
            except Exception as e:
                click.echo(_c("red", f"\n❌ LUA error: {e}"))
                return

    # ── STEP 6: Stop Conditions (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('bold')}STOP CONDITIONS{_c('reset')}               {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")
    max_bets, sp, sl = 0, 0.0, 0.0
    if click.confirm("⏹️  Set stop conditions?", default=False):
        max_bets = click.prompt("  Max bets (0=∞)", type=int, default=0)
        sp = click.prompt("  Stop profit (0=∞)", type=float, default=0.0)
        sl = click.prompt("  Stop loss (0=∞)", type=float, default=0.0)

    # ── STEP 7: Summary & Confirm (clear screen) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔══════════════════════════════════╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {_c('yellow')}RINGKASAN{_c('reset')}                    {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╠══════════════════════════════════╣{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {'🎲 DICE' if game_type == 'dice' else '🚀 LIMBO'}{' '*26}{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  Coin:      {coin.upper()}{' '*22}{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  Base Bet:  {bb:.8f}{' '*21}{_c('cyan')}║{_c('reset')}")
    if game_type == "dice":
        click.echo(f"{_c('cyan')}║{_c('reset')}  Chance:    {target}%{' '*23}{_c('cyan')}║{_c('reset')}")
        click.echo(f"{_c('cyan')}║{_c('reset')}  Roll:      {condition}{' '*23}{_c('cyan')}║{_c('reset')}")
    else:
        click.echo(f"{_c('cyan')}║{_c('reset')}  Target:    {target}x{' '*24}{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  Script:    {script_name}{' '*22}{_c('cyan')}║{_c('reset')}")
    if max_bets > 0:
        click.echo(f"{_c('cyan')}║{_c('reset')}  Max Bets:  {max_bets}{' '*22}{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚══════════════════════════════════╝{_c('reset')}\n")

    if not click.confirm(f"  {_c('yellow', '🔥 RUN?')}", default=True):
        click.echo(_c("dim", "\n  Batal."))
        return

    # ── STEP 8: RUN! ──
    bc = BetConfig(
        game=game_type, coin=coin.lower(), base_bet=bb,
        target=target, condition=condition,
        max_bets=max_bets, stop_profit=sp, stop_loss=sl,
    )
    logger = SessionLogger(game_type, coin.lower(), bb, script_name)

    asyncio.run(_run_live(cfg, bc, lua_engine, player_name, logger))


async def _run_live(cfg: StakeConfig, bc: BetConfig, lua,
                    player_name: str, logger: SessionLogger):
    """Run betting session with live display + session logging."""
    async with StakeClient(cfg) as client:
        # Verify auth again (belt + suspenders)
        try:
            user = await client.get_user()
        except AuthError:
            _cls()
            click.echo(_c("red", "\n❌ Token expired!"))
            return
        except ConnectionError:
            _cls()
            click.echo(_c("red", "\n❌ Gagal koneksi!"))
            return

        bal = client.balance.get(bc.coin, 0)
        if bal < bc.base_bet:
            _cls()
            click.echo(_c("red", f"\n❌ Saldo {bc.coin.upper()} tidak cukup!"))
            click.echo(f"Saldo: {bal:.8f}  |  Bet: {bc.base_bet:.8f}")
            return

        # Initialize live display
        display = LiveDisplay(bc.game, bc.coin, player_name)
        display.init()

        stop_reason = ""

        # Shared state for tracking current bet amount
        current_bet = [bc.base_bet]

        async def on_bet(stats, result):
            """Update live display + log each bet."""
            won = result.get("won", False)
            payout = result.get("payout", 0)
            amount = current_bet[0]

            # Update balance
            if bc.coin in client.balance:
                stats.current_balance = client.balance[bc.coin]
            else:
                stats.current_balance += (payout - amount) if won else -amount

            # Build last-result line
            if bc.game == "dice":
                roll = result.get("result", 0)
                last = f"{'✅ WON' if won else '❌ LOST'}  {_c('dim')}Roll:{_c('reset')} {roll:.1f}  {_c('dim')}Payout:{_c('reset')} {payout:.8f}"
            else:
                crash = result.get("crash_point", 0)
                last = f"{'✅ WON' if won else '❌ LOST'}  {_c('dim')}Crash:{_c('reset')} {crash:.2f}x  {_c('dim')}Payout:{_c('reset')} {payout:.8f}"

            # Update live display
            display.update(
                bet_id=stats.bets,
                won=won,
                streak=stats.streak,
                profit=stats.profit,
                balance=stats.current_balance,
                bet_amount=amount,
                winrate=stats.winrate,
                last_result=last,
                payout=payout,
            )

            # Log to file
            logger.record(
                bet_id=stats.bets,
                amount=amount,
                target=bc.target,
                condition=bc.condition,
                won=won,
                payout=payout,
                profit=stats.profit,
                streak=stats.streak,
                balance=stats.current_balance,
                result_raw=result,
            )

        # Wrap engine._place_bet to track current bet amount
        engine = BettingEngine(client=client, config=bc, lua_engine=lua)
        original_place = engine._place_bet

        async def tracked_place_bet(amount, target, condition):
            current_bet[0] = amount
            return await original_place(amount, target, condition)

        engine._place_bet = tracked_place_bet
        bc.on_bet = on_bet

        try:
            stats = await engine.run()
            # Check why we stopped
            if bc.max_bets > 0 and stats.bets >= bc.max_bets:
                stop_reason = "Max bets reached"
            elif bc.stop_profit > 0 and stats.profit >= bc.stop_profit:
                stop_reason = "Target profit reached"
            elif bc.stop_loss > 0 and stats.profit <= -bc.stop_loss:
                stop_reason = "Stop loss triggered"
        except KeyboardInterrupt:
            engine.stop()
            await asyncio.sleep(0.3)
            stats = engine.stats
            stop_reason = "User interrupted"

        # Save log
        logger.save()

        # Show summary
        _show_summary(stats, bc, logger, stop_reason)


# ── Entry ──

def main():
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "run"]
    cli()


if __name__ == "__main__":
    main()
