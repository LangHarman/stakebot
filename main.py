#!/usr/bin/env python3
"""
StakeBot CLI v{VERSION} — Professional Taraje-Compatible Betting Bot
🎲 Dice | 🚀 Limbo | 📜 LUA Scripts
"""
from __future__ import annotations

import asyncio
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

# ── ANSI ──

def _c(code: str, text="") -> str:
    colors = {"cyan":"36","green":"32","yellow":"33","red":"31",
              "white":"97","magenta":"35","dim":"2","bold":"1","reset":"0"}
    return f"\033[{colors.get(code,'0')}m{text}\033[0m"

def _cls():
    click.echo("\033[H\033[2J\033[3J", nl=False)

def _banner():
    click.echo(f"\n{_c('bold')}  🎲 StakeBot v{VERSION}{_c('reset')}")
    click.echo(f"{_c('dim')}  Dice / Limbo / Crash / LUA Scripts{_c('reset')}\n")

def _pick(prompt: str, choices: list[str], default: int = 1) -> str:
    click.echo(_c("yellow", prompt))
    for i, ch in enumerate(choices, 1):
        m = _c("cyan", "▶") if i == default else " "
        click.echo(f"  {m} {_c('white', str(i))}. {ch}")
    val = click.prompt(f"  pilihan (1-{len(choices)})", type=int,
                       default=default, show_default=False)
    return choices[min(max(val, 1), len(choices)) - 1]

def _read_multiline(prompt: str = "  > ") -> str:
    click.echo(_c("dim", "  (paste, lalu Enter kosong untuk selesai)"))
    lines = []
    while True:
        try:
            line = input(prompt)
            if line.strip() == "":
                if lines: break
            else:
                lines.append(line.strip())
        except (EOFError, KeyboardInterrupt): break
    return "\n".join(lines)


# ═════════════════════════════════════════════
#  SPLASH SCREEN
# ═════════════════════════════════════════════

SPLASH = """


  {y}▗▄▄▖ ▗▄▖▗▄▄▄▖▗▄▖ ▗▖ ▗▖▗▄▄▄▖ ▗▄▖ ▗▖ ▗▖{R}
  {y}▐▌ ▐▌▐▌ ▐▌ █ ▐▌ ▐▌▐▌ ▐▌ █ ▐▌ ▐▌▐▛▚▖▐▌{R}
  {y}▐▛▀▚▖▐▛▀▜▌ █ ▐▛▀▜▌▐▌ ▐▌ █ ▐▛▀▜▌▐▌ ▝▜▌{R}
  {y}▐▙▄▞▘▐▌ ▐▌ █ ▐▌ ▐▌ ▝▚▞▘ ▗▄█▄▖▐▌ ▐▌▐▌ ▐▌{R}




          {y}▗▖ ▗▄▖ ▗▖ ▗▖▗▄▄▄▖▗▄▄▖{R}
           {y}▐▌▐▌ ▐▌▐▌▗▞▘▐▌ ▐▌ ▐▌{R}
          {y}▐▌▐▛▀▜▌▐▛▚▖ ▐▛▀▀▘▐▛▀▚▖{R}
        {y}▗▄▄▞▘▐▌ ▐▌▐▌ ▐▌▐▙▄▄▖▐▌ ▐▌{R}



{m}       Winner know when to stop!{R}

{g}        Stake Bot v{VERSION}{R}
{d}   Made by Melky & Batavian Jaker{R}

{d}             2026{R}


       {d}Connecting...{R}
"""

def _splash():
    """Display splash screen for 2.5 seconds."""
    _cls()
    txt = (SPLASH
           .replace("{y}", _c("yellow"))
           .replace("{m}", _c("magenta"))
           .replace("{g}", _c("green"))
           .replace("{d}", _c("dim"))
           .replace("{R}", _c("reset"))
           .replace("{VERSION}", VERSION))
    click.echo(txt)
    time.sleep(2.5)


# ═════════════════════════════════════════════
#  LIVE DISPLAY
# ═════════════════════════════════════════════

class LiveDisplay:
    """Real-time betting display — compact 1-line updates with phase indicator."""

    def __init__(self, game: str, coin: str, name: str):
        self.game = game
        self.coin = coin
        self.name = name
        self._header = False
        self._prev_won = True  # track streak for coloring

    def init(self):
        _cls()
        gnames = {"limbo": "🚀 LIMBO", "dice": "🎲 DICE", "crash": "💥 CRASH"}
        gname = gnames.get(self.game, self.game.upper())
        click.echo(f"{_c('yellow', gname)} {_c('dim', 'LIVE')} — {_c('green', self.name)} | {self.coin.upper()}")
        click.echo(f"{_c('dim', '#    Target Result Bet        PnL          Balance      Wager       W/L')}")
        click.echo(f"{_c('dim', '─'*80)}")
        self._header = True

    def update(self, bet_id: int, won: bool, amount: float, target: float = 0,
               result: float = 0, pnl: float = 0, balance: float = 0,
               total_wagered: float = 0, phase: int = 0):
        # Color logic for bet amount
        if not won:
            amt_col = "red"          # loss streak
        elif not self._prev_won:
            amt_col = "yellow"       # win after loss streak — recovery!
        else:
            amt_col = ""             # normal white
        self._prev_won = won

        pcol = "green" if pnl >= 0 else "red"
        pnl_s = f"{pnl:+.8f}" if pnl >= 0 else f"{pnl:.8f}"
        won_s = _c("green", "W") if won else _c("red", "L")

        # Phase indicator (W=Wager, R=Recovery, P=Paus, ·=none)
        if phase == 1:
            phase_s = _c("green", "W")     # Wager
        elif phase == 2:
            phase_s = _c("yellow", "R")    # Recovery
        elif phase == 3:
            phase_s = _c("magenta", "P")   # Paus
        else:
            phase_s = _c("dim", "·")

        line = (f"{phase_s} "
                f"#{bet_id:<5}"
                f"{target:5.2f} "
                f"{result:6.2f} "
                f"{_c(amt_col, f'{amount:.8f}')}  "
                f"{_c(pcol, pnl_s)}  "
                f"{balance:.8f}  "
                f"{total_wagered:.8f}  "
                f"{won_s}")
        click.echo(line)


# ═════════════════════════════════════════════
#  SUMMARY
# ═════════════════════════════════════════════

def _summary(stats, bc: BetConfig, logger: SessionLogger, reason: str):
    _cls()
    pcol = "green" if stats.profit >= 0 else "red"
    gnames = {"limbo": "🚀 LIMBO", "dice": "🎲 DICE", "crash": "💥 CRASH"}
    lines = [
        f"{_c('cyan')}╔{'═'*44}╗{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}          {_c('yellow')}SESSION SUMMARY{_c('reset')}                  {_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}╠{'═'*44}╣{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Game:{_c('reset')}  {gnames.get(bc.game, bc.game)}" + " " * 29 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Coin:{_c('reset')}  {bc.coin.upper()}" + " " * 34 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Base Bet:{_c('reset')} {bc.base_bet:.8f}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}╠{'═'*44}╣{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Bets:{_c('reset')} {stats.bets}" + " " * 34 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('green')}✅ Wins:{_c('reset')}   {stats.wins}" + " " * 28 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('red')}❌ Losses:{_c('reset')}  {stats.losses}" + " " * 28 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Winrate:{_c('reset')} {stats.winrate:.1f}%" + " " * 27 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Profit:{_c('reset')} {_c(pcol, f'{stats.profit:+.8f}')} {bc.coin.upper()}" + " " * 17 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Best Streak:{_c('reset')} +{stats.best_streak}" + " " * 25 + f"{_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Worst Streak:{_c('reset')} {stats.worst_streak}" + " " * 25 + f"{_c('cyan')}║{_c('reset')}",
    ]
    if reason:
        lines.append(f"{_c('cyan')}╠{'═'*44}╣{_c('reset')}")
        lines.append(f"{_c('cyan')}║{_c('reset')}  {_c('red')}STOP: {reason}{_c('reset')}" + " " * (38-len(reason)) + f"{_c('cyan')}║{_c('reset')}")
    lines += [
        f"{_c('cyan')}╚{'═'*44}╝{_c('reset')}",
        f"  {_c('dim')}Log: {logger.path}{_c('reset')}",
    ]
    click.echo("\n".join(lines))


# ═════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════

def _load_cfg() -> StakeConfig:
    return StakeConfig.load()

def _need_token(cfg: StakeConfig) -> bool:
    if not cfg.is_configured:
        click.echo(_c("red", "\n❌ Belum ada token!"))
        click.echo(f"  Jalankan: {_c('white', 'python main.py curl')}")
        return False
    return True


# ═════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@cli.command()
def auth():
    _cls(); _banner()
    m = _pick("🌐 Mirror:", ["auto","stake.mba","stake.com","playstake.club","custom"],1)
    if "auto" in m: url, mode = "https://stake.com", True
    elif "custom" in m:
        u = click.prompt("  URL", default="stake.mba")
        url = f"https://{u}" if not u.startswith("http") else u; mode = False
    else: url, mode = f"https://{m}", False
    click.echo(f"  → {_c('green', url)}")
    token = click.prompt(f"\n🔑 x-access-token", hide_input=True)
    StakeConfig(access_token=token, base_url=url, mirror_mode=mode).save()
    click.echo(_c("green", "\n✅ Tersimpan!"))


@cli.command()
def curl():
    _cls(); _banner()
    click.echo(_c("yellow", "📋 Copy as cURL dari browser:"))
    click.echo(textwrap.dedent(f"""
      {_c('dim', '1.')} Buka stake.mba → login
      {_c('dim', '2.')} DevTools → Network → filter: graphql
      {_c('dim', '3.')} Right-click /_api/graphql → Copy as cURL
    """))
    ct = _read_multiline()
    if not ct.strip(): click.echo(_c("red", "❌ Kosong!")); return
    p = parse_curl(ct)
    token = p.get("access_token","")
    if not token:
        click.echo(_c("red", f"\n❌ Token tidak ditemukan! Input: {ct[:80]}"))
        return
    cookie = p.get("session_cookie","")
    url = p.get("url","https://stake.com")
    mirror_url = "https://stake.com"
    for m in MIRRORS:
        if m in url: mirror_url = m; break
    StakeConfig(access_token=token, session_cookie=cookie,
                base_url=mirror_url, mirror_mode=True).save()
    click.echo(_c("green", f"\n✅ Tersimpan! Token: {token[:12]}...{token[-6:]}"))


@cli.command()
def balance():
    _cls(); _banner()
    cfg = _load_cfg()
    if not _need_token(cfg): return
    async def _b():
        try:
            async with StakeClient(cfg) as client:
                u = await client.get_user()
                click.echo(_c("green", f"  👤 {u['name']}"))
                click.echo(f"  {'─'*30}")
                for c, a in sorted(client.balance.items(), key=lambda x: -x[1]):
                    if a > 0: click.echo(f"  {c.upper():>6}  {a:.8f}")
        except AuthError: click.echo(_c("red", "\n❌ Token expired!"))
        except ConnectionError: click.echo(_c("red", "\n❌ Gagal connect!"))
    asyncio.run(_b())


@cli.command()
def test():
    _cls(); _banner()
    cfg = _load_cfg()
    if not _need_token(cfg): return
    async def _t():
        click.echo(_c("yellow", "🔍 Mencoba mirror...\n"))
        async with StakeClient(cfg) as client:
            for url in MIRRORS:
                try:
                    click.echo(f"  {_c('dim', url + ':')} ", nl=False)
                    r = await client._try_url(url, "{ user { id name } }", {})
                    if r: click.echo(_c("green", "✅ OK")); return
                    else: click.echo(_c("red", "❌"))
                except: click.echo(_c("red", "❌"))
            click.echo(f"\n{_c('red', '❌ Semua diblokir!')}")
    asyncio.run(_t())


@cli.command()
def history():
    _cls(); _banner()
    sessions = list_sessions(15)
    if not sessions: click.echo(_c("dim", "  Belum ada riwayat.")); return
    click.echo(f"{_c('yellow', '📋 Sesi terakhir:')}\n")
    for i, s in enumerate(sessions[:10], 1):
        try:
            sm = read_summary(s)
            profit = sm.get("profit",0)
            p = _c("green", f"+{profit:.6f}") if profit>=0 else _c("red", f"{profit:.6f}")
            ts = s.stem.replace("session_","")
            d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}"
            click.echo(f"  {i:>2}. {_c('dim', d)}  {sm.get('game','?'):5} {sm.get('coin','?'):6}  ✅{sm.get('wins',0)}/❌{sm.get('losses',0)}  {p}")
        except: click.echo(f"  {i:>2}. {_c('dim', s.stem)}")


# ═════════════════════════════════════════════
#  MAIN RUN
# ═════════════════════════════════════════════

@cli.command()
def run():
    # ── Splash ──
    _splash()
    _cls()

    cfg = _load_cfg()
    if not _need_token(cfg):
        return

    async def _verify():
        async with StakeClient(cfg) as c:
            return await c.get_user()

    try: user = asyncio.run(_verify())
    except AuthError:
        click.echo(_c("red", "\n❌ Token expired!")); return
    except ConnectionError:
        click.echo(_c("red", "\n❌ Gagal koneksi!")); return

    name = user.get("name", "Player")

    # ── Game ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}      {_c('bold')}PILIH GAME{_c('reset')}              {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    game = _pick("", ["🎲 Dice", "🚀 Limbo", "💥 Crash"], 1)
    if "Limbo" in game: gt = "limbo"
    elif "Crash" in game: gt = "crash"
    else: gt = "dice"

    # ── Coin ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}      {_c('bold')}PILIH COIN{_c('reset')}              {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    coin = _pick("", ["USDT","LTC","BTC","ETH","SOL","DOGE","TRX","BNB","Lainnya"],1)
    if coin == "Lainnya": coin = click.prompt("  Kode", default="DOT").upper()

    # ── Strategi (tanya dulu: LUA atau Web) ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('bold')}BET SET{_c('reset')}                {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    lua_engine = None; script_name = "web"
    bets_type = _pick("", ["🌐 Web Based (auto-bet)", "📜 Script Lua"], 1)
    defs = {"BTC":1e-8,"ETH":1e-5,"USDT":0.01,"LTC":0.001,"SOL":0.001,"DOGE":1.0,"TRX":1.0}
    target = 2.0; condition = "above"
    owr = True; owp = 0.0; olr = False; olp = 100.0

    if "Lua" in bets_type:
        # ── LUA Script ──
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem.replace("_"," ").title() for s in scripts]
            chosen = _pick("  Script", snames, 1)
            idx = snames.index(chosen); script_name = scripts[idx].stem
            try: lua_engine = LuaScriptEngine(scripts[idx].read_text())
            except Exception as e:
                click.echo(_c("red", f"\n❌ LUA: {e}")); return
        else:
            click.echo(_c("red", "\n❌ Tidak ada script .lua")); return
        bb = 0.0  # Lua script controls bet amount

    else:
        # ── Web Based: Base Bet ──
        _cls()
        click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
        click.echo(f"{_c('cyan')}║{_c('reset')}    {_c('bold')}BET AMOUNT ({coin}){_c('reset')}         {_c('cyan')}║{_c('reset')}")
        click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
        bb = click.prompt("  💰 Amount", type=float, default=defs.get(coin, 0.01))

        # ── Web Based: Target ──
        _cls()
        click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
        click.echo(f"{_c('cyan')}║{_c('reset')}      {_c('bold')}TARGET{_c('reset')}                {_c('cyan')}║{_c('reset')}")
        click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
        if gt == "dice":
            target = click.prompt("  🎯 Chance (%)", type=float, default=49.5)
            cond = _pick("  📈 Roll:", ["Above", "Below"], 1)
            condition = cond.lower()
        else:
            target = click.prompt("  🎯 Multiplier (x)", type=float, default=2.0)
            condition = "above"

        # ── Web Based: On Win ──
        _cls()
        click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
        click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('bold')}ON WIN{_c('reset')}                 {_c('cyan')}║{_c('reset')}")
        click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
        win_act = _pick("", ["Reset to base bet", "Increase by %"], 1)
        owr = win_act == "Reset to base bet"
        if not owr:
            owp = click.prompt("  Increase by %", type=float, default=100.0)

        # ── Web Based: On Lose ──
        _cls()
        click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
        click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('bold')}ON LOSE{_c('reset')}                {_c('cyan')}║{_c('reset')}")
        click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
        lose_act = _pick("", ["Increase by % (martingale)", "Reset to base bet"], 1)
        olr = lose_act == "Reset to base bet"
        if not olr:
            olp = click.prompt("  Increase by %", type=float, default=100.0)

    # ── Stop ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}   {_c('bold')}STOP CONDITIONS{_c('reset')}         {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    mx, sp, sl = 0, 0.0, 0.0
    if click.confirm("⏹️  Set?", default=False):
        mx = click.prompt("  Max bets (0=∞)", type=int, default=0)
        sp = click.prompt("  Stop profit (0=∞)", type=float, default=0.0)
        sl = click.prompt("  Stop loss (0=∞)", type=float, default=0.0)

    # ── Confirm ──
    _cls()
    gnames = {"limbo": "🚀 LIMBO", "dice": "🎲 DICE", "crash": "💥 CRASH"}
    is_lua = lua_engine is not None
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('yellow')}RINGKASAN{_c('reset')}              {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╠{'═'*30}╣{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {gnames.get(gt, gt)}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {coin.upper()}" + " " * 30 + f"{_c('cyan')}║{_c('reset')}")
    if is_lua:
        click.echo(f"{_c('cyan')}║{_c('reset')}  Script: {script_name}" + " " * 22 + f"{_c('cyan')}║{_c('reset')}")
    else:
        click.echo(f"{_c('cyan')}║{_c('reset')}  Bet: {bb:.8f}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}")
        if gt == "dice":
            click.echo(f"{_c('cyan')}║{_c('reset')}  Target: {target}% {condition}" + " " * 16 + f"{_c('cyan')}║{_c('reset')}")
        else:
            click.echo(f"{_c('cyan')}║{_c('reset')}  Target: {target}x" + " " * 22 + f"{_c('cyan')}║{_c('reset')}")
        ow = "Reset" if owr else f"+{owp:.0f}%"
        ol = "Reset" if olr else f"+{olp:.0f}%"
        click.echo(f"{_c('cyan')}║{_c('reset')}  On Win: {ow} / Lose: {ol}" + " " * 11 + f"{_c('cyan')}║{_c('reset')}")
    if mx: click.echo(f"{_c('cyan')}║{_c('reset')}  Max bets: {mx}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}")
    if sp: click.echo(f"{_c('cyan')}║{_c('reset')}  Stop profit: {sp}" + " " * 20 + f"{_c('cyan')}║{_c('reset')}")
    if sl: click.echo(f"{_c('cyan')}║{_c('reset')}  Stop loss: {sl}" + " " * 22 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    loop_enabled = click.confirm("  🔄 Looping?", default=False)
    if not click.confirm(f"  {_c('yellow', '🔥 RUN?')}", default=True):
        return

    bc = BetConfig(game=gt, coin=coin.lower(), base_bet=bb,
                   target=target, condition=condition,
                   max_bets=mx, stop_profit=sp, stop_loss=sl,
                   on_win_reset=owr, on_win_pct=owp,
                   on_lose_reset=olr, on_lose_pct=olp)
    logger = SessionLogger(gt, coin.lower(), bb, script_name)
    asyncio.run(_run_live(cfg, bc, lua_engine, name, logger, loop_enabled))


async def _run_live(cfg: StakeConfig, bc: BetConfig, lua,
                    name: str, logger: SessionLogger, loop_enabled: bool = False):
    async with StakeClient(cfg) as client:
        try: user = await client.get_user()
        except AuthError: _cls(); click.echo(_c("red","\n❌ Token expired!")); return
        except ConnectionError: _cls(); click.echo(_c("red","\n❌ Gagal koneksi!")); return

        bal = client.balance.get(bc.coin, 0)
        if bal < bc.base_bet and not lua:
            _cls()
            click.echo(_c("red", f"\n❌ Saldo {bc.coin.upper()} tidak cukup!"))
            return

        # Show starting balance
        click.echo(_c("dim", f"  💰 Balance: {bal:.8f} {bc.coin.upper()}"))
        if bal <= 0 and not lua:
            _cls()
            click.echo(_c("red", f"\n❌ Saldo {bc.coin.upper()} = 0, tidak bisa bet!"))
            return

        display = LiveDisplay(bc.game, bc.coin, name)
        display.init()

        loop_count = 0
        error_count = [0]
        current_balance = bal

        async def _on_error(msg: str):
            error_count[0] += 1
            if error_count[0] <= 3:
                click.echo(_c("red", f"  ⚠️  {msg}"))
        cbet = [bc.base_bet]
        ctarget = [bc.target]
        last_target = [bc.target]

        while True:
            loop_count += 1
            cbet[0] = bc.base_bet
            ctarget[0] = bc.target

            async def on_bet(stats, result):
                won = result.get("won", False)
                payout = result.get("payout", 0)
                amount = cbet[0]
                target = ctarget[0]
                roll = result.get("result", result.get("crash_point", 0))
                # Always track manually — client.balance is stale between bets
                stats.current_balance += (payout - amount) if won else -amount

                # Phase indicator (Lua script only)
                cur_phase = lua.get("phase") if lua else 0

                # Phase change separator (target shift >= 0.2 = new phase)
                if abs(target - last_target[0]) >= 0.2:
                    click.echo()
                last_target[0] = target

                display.update(bet_id=stats.bets, won=won, amount=amount,
                              target=target, result=roll,
                              pnl=stats.profit, balance=stats.current_balance,
                              total_wagered=stats.total_wagered, phase=cur_phase)

                logger.record(bet_id=stats.bets, amount=amount, target=bc.target,
                             condition=bc.condition, won=won, payout=payout,
                             profit=stats.profit, streak=stats.streak,
                             balance=stats.current_balance, result_raw=result)

            engine = BettingEngine(client=client, config=bc, lua_engine=lua)
            orig = engine._place_bet
            async def _tp(amount, target, condition):
                cbet[0] = amount; ctarget[0] = target; return await orig(amount, target, condition)
            engine._place_bet = _tp
            bc.on_bet = on_bet
            bc.on_error = _on_error

            reason = ""
            error_count[0] = 0
            try:
                stats = await engine.run(initial_balance=current_balance)
            except KeyboardInterrupt:
                engine.stop(); await asyncio.sleep(0.3); stats = engine.stats; reason = "User interrupted"
            except ConnectionError as e:
                click.echo(_c("red", f"\n❌ {e}"))
                stats = engine.stats; reason = str(e)

            # Update running balance for next loop
            if stats.current_balance > 0:
                current_balance = stats.current_balance

            if not reason:
                if bc.max_bets > 0 and stats.bets >= bc.max_bets: reason = "Max bets reached"
                elif bc.stop_profit > 0 and stats.profit >= bc.stop_profit: reason = "Target profit reached"
                elif bc.stop_loss > 0 and stats.profit <= -bc.stop_loss: reason = "Stop loss triggered"

            logger.save()
            _summary(stats, bc, logger, reason)

            # If no bets placed, don't loop — something is wrong
            if stats.bets == 0 and loop_enabled:
                click.echo(_c("red", "\n❌ 0 bets placed — stopping loop"))
                break

            if not loop_enabled:
                break

            # Re-init for next loop
            click.echo(f"\n{_c('dim', '─'*70)}")
            click.echo(f"{_c('yellow', f'🔄 LOOP #{loop_count+1}')} {_c('dim', '— restarting from base bet...')}")
            logger = SessionLogger(bc.game, bc.coin, bc.base_bet, logger.script_name)
            if lua:
                lua.set("balance", stats.current_balance)
                lua.call("init")


def main():
    if len(sys.argv) == 1: sys.argv = [sys.argv[0], "run"]
    cli()

if __name__ == "__main__":
    main()
