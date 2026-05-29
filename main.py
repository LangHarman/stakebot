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
    click.echo(f"{_c('dim')}  Dice / Limbo / LUA Scripts{_c('reset')}\n")

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
    """Real-time betting display — updates in-place."""

    def __init__(self, game: str, coin: str, name: str):
        self.game = game
        self.coin = coin
        self.name = name
        self._lines = 0

    def init(self):
        _cls()
        icon = "🚀" if self.game == "limbo" else "🎲"
        gname = "LIMBO" if self.game == "limbo" else "DICE"
        bar = f"{_c('cyan')}{'═'*42}{_c('reset')}"
        lines = [
            f"{_c('cyan')}╔{'═'*42}╗{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {icon} {_c('yellow')}{gname} LIVE{_c('reset')} — {_c('green')}{self.name}{_c('reset')}" + " " * 15 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╠{'═'*42}╣{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Starting...{_c('reset')}" + " " * 30 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╚{'═'*42}╝{_c('reset')}",
        ]
        click.echo("\n".join(lines))
        self._lines = 5

    def update(self, bet_id: int, won: bool, streak: int, profit: float,
               balance: float, amount: float, winrate: float,
               last: str, payout: float):
        pcol = "green" if profit >= 0 else "red"
        scol = "red" if streak < 0 else "green"
        ssign = "" if streak < 0 else "+"
        lines = [
            f"{_c('cyan')}╔{'═'*42}╗{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  #{bet_id} {'✅' if won else '❌'}  {_c('dim')}S:{_c('reset')}{_c(scol, ssign + str(streak))}  {_c('dim')}P:{_c('reset')}{_c(pcol, f'{profit:+.8f}')}  {_c('dim')}WR:{_c('reset')}{winrate:.0f}%   {_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Bet:{_c('reset')} {amount:.8f}  {_c('dim')}Bal:{_c('reset')} {balance:.8f} {self.coin.upper()}" + " " * 6 + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╠{'═'*42}╣{_c('reset')}",
            f"{_c('cyan')}║{_c('reset')}  {last}" + " " * (42 - len(last)) + f"{_c('cyan')}║{_c('reset')}",
            f"{_c('cyan')}╚{'═'*42}╝{_c('reset')}",
        ]
        if self._lines > 0:
            click.echo(f"\033[{self._lines}A", nl=False)
        click.echo("\n".join(lines))
        self._lines = 6


# ═════════════════════════════════════════════
#  SUMMARY
# ═════════════════════════════════════════════

def _summary(stats, bc: BetConfig, logger: SessionLogger, reason: str):
    _cls()
    pcol = "green" if stats.profit >= 0 else "red"
    bar = f"{_c('cyan')}{'═'*44}{_c('reset')}"
    lines = [
        f"{_c('cyan')}╔{'═'*44}╗{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}          {_c('yellow')}SESSION SUMMARY{_c('reset')}                  {_c('cyan')}║{_c('reset')}",
        f"{_c('cyan')}╠{'═'*44}╣{_c('reset')}",
        f"{_c('cyan')}║{_c('reset')}  {_c('dim')}Game:{_c('reset')}  {'🚀 LIMBO' if bc.game == 'limbo' else '🎲 DICE'}" + " " * 29 + f"{_c('cyan')}║{_c('reset')}",
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
    game = _pick("", ["🎲 Dice", "🚀 Limbo"], 1)
    gt = "limbo" if "Limbo" in game else "dice"

    # ── Coin ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}      {_c('bold')}PILIH COIN{_c('reset')}              {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    coin = _pick("", ["USDT","LTC","BTC","ETH","SOL","DOGE","TRX","BNB","Lainnya"],1)
    if coin == "Lainnya": coin = click.prompt("  Kode", default="DOT").upper()

    # ── Base Bet ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}    {_c('bold')}BASE BET ({coin}){_c('reset')}          {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    defs = {"BTC":1e-8,"ETH":1e-5,"USDT":0.01,"LTC":0.001,"SOL":0.001,"DOGE":1.0,"TRX":1.0}
    bb = click.prompt("  💰 Amount", type=float, default=defs.get(coin, 0.01))

    # ── Target ──
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

    # ── Script ──
    _cls()
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('bold')}STRATEGI{_c('reset')}               {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    lua_engine = None; script_name = "manual"
    if click.confirm("📜 LUA script?", default=True):
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem.replace("_"," ").title() for s in scripts]
            chosen = _pick("", snames, 1)
            idx = snames.index(chosen); script_name = scripts[idx].stem
            try: lua_engine = LuaScriptEngine(scripts[idx].read_text())
            except Exception as e:
                click.echo(_c("red", f"\n❌ LUA: {e}")); return

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
    click.echo(f"\n{_c('cyan')}╔{'═'*30}╗{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}     {_c('yellow')}RINGKASAN{_c('reset')}              {_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╠{'═'*30}╣{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {'🎲 DICE' if gt=='dice' else '🚀 LIMBO'}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  {coin.upper()}" + " " * 30 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  Bet: {bb:.8f}" + " " * 23 + f"{_c('cyan')}║{_c('reset')}")
    if gt == "dice":
        click.echo(f"{_c('cyan')}║{_c('reset')}  Target: {target}% {condition}" + " " * 16 + f"{_c('cyan')}║{_c('reset')}")
    else:
        click.echo(f"{_c('cyan')}║{_c('reset')}  Target: {target}x" + " " * 22 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}║{_c('reset')}  Script: {script_name}" + " " * 22 + f"{_c('cyan')}║{_c('reset')}")
    click.echo(f"{_c('cyan')}╚{'═'*30}╝{_c('reset')}\n")
    if not click.confirm(f"  {_c('yellow', '🔥 RUN?')}", default=True):
        return

    bc = BetConfig(game=gt, coin=coin.lower(), base_bet=bb,
                   target=target, condition=condition,
                   max_bets=mx, stop_profit=sp, stop_loss=sl)
    logger = SessionLogger(gt, coin.lower(), bb, script_name)
    asyncio.run(_run_live(cfg, bc, lua_engine, name, logger))


async def _run_live(cfg: StakeConfig, bc: BetConfig, lua,
                    name: str, logger: SessionLogger):
    async with StakeClient(cfg) as client:
        try: user = await client.get_user()
        except AuthError: _cls(); click.echo(_c("red","\n❌ Token expired!")); return
        except ConnectionError: _cls(); click.echo(_c("red","\n❌ Gagal koneksi!")); return

        bal = client.balance.get(bc.coin, 0)
        if bal < bc.base_bet:
            _cls()
            click.echo(_c("red", f"\n❌ Saldo {bc.coin.upper()} tidak cukup!"))
            return

        display = LiveDisplay(bc.game, bc.coin, name)
        display.init()

        cbet = [bc.base_bet]

        async def on_bet(stats, result):
            won = result.get("won", False)
            payout = result.get("payout", 0)
            amount = cbet[0]
            if bc.coin in client.balance:
                stats.current_balance = client.balance[bc.coin]
            else:
                stats.current_balance += (payout - amount) if won else -amount

            if bc.game == "dice":
                last = f"{'✅ WON' if won else '❌ LOST'}  Roll: {result.get('result',0):.1f}  Payout: {payout:.8f}"
            else:
                last = f"{'✅ WON' if won else '❌ LOST'}  Crash: {result.get('crash_point',0):.2f}x  Payout: {payout:.8f}"

            display.update(bet_id=stats.bets, won=won, streak=stats.streak,
                          profit=stats.profit, balance=stats.current_balance,
                          amount=amount, winrate=stats.winrate,
                          last=last, payout=payout)

            logger.record(bet_id=stats.bets, amount=amount, target=bc.target,
                         condition=bc.condition, won=won, payout=payout,
                         profit=stats.profit, streak=stats.streak,
                         balance=stats.current_balance, result_raw=result)

        engine = BettingEngine(client=client, config=bc, lua_engine=lua)
        orig = engine._place_bet
        async def _tp(amount, target, condition):
            cbet[0] = amount; return await orig(amount, target, condition)
        engine._place_bet = _tp
        bc.on_bet = on_bet

        reason = ""
        try: stats = await engine.run()
        except KeyboardInterrupt: engine.stop(); await asyncio.sleep(0.3); stats = engine.stats; reason = "User interrupted"

        if not reason:
            if bc.max_bets > 0 and stats.bets >= bc.max_bets: reason = "Max bets reached"
            elif bc.stop_profit > 0 and stats.profit >= bc.stop_profit: reason = "Target profit reached"
            elif bc.stop_loss > 0 and stats.profit <= -bc.stop_loss: reason = "Stop loss triggered"

        logger.save()
        _summary(stats, bc, logger, reason)


def main():
    if len(sys.argv) == 1: sys.argv = [sys.argv[0], "run"]
    cli()

if __name__ == "__main__":
    main()
