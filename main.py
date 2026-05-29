"""
StakeBot — CLI entry point.
Inspired by Taraje's CLI + interactive prompts for HP users.
"""
import asyncio
import json
import sys
from pathlib import Path

import click
from colorama import init, Fore, Style

from core.client import (
    StakeClient, StakeConfig, StakeConfigManager,
    KNOWN_MIRRORS,
)
from core.engine import BettingEngine, BetConfig, BetStats
from core.script_engine import LuaScriptEngine

init(autoreset=True)

BANNER = f"""
{Fore.CYAN}╔══════════════════════════════════════╗
║     {Fore.YELLOW}StakeBot v2.8 — Taraje Compatible{Fore.CYAN}     ║
║     {Fore.WHITE}Dice 🎲  |  Limbo 🚀{Fore.CYAN}               ║
╚══════════════════════════════════════╝{Fore.RESET}
"""

SCRIPT_DIR = Path(__file__).parent / "scripts"


# ── Helpers ──

def load_cfg() -> StakeConfig:
    """Load saved config, return empty cfg if missing."""
    return StakeConfigManager.load()


def apply_mirror(cfg: StakeConfig, mirror_opt: str):
    """Apply mirror option to config."""
    if mirror_opt and mirror_opt != "auto" and mirror_opt != "none":
        cfg.base_url = f"https://{mirror_opt}"
        cfg.mirror_mode = False
    elif mirror_opt == "auto":
        cfg.mirror_mode = True


def msg_no_token():
    """Show instructions when no token saved."""
    click.echo(f"\n{Fore.YELLOW}⚠️  Belum ada config! Jalankan dulu:{Fore.RESET}")
    click.echo(f"  {Fore.WHITE}python main.py auth{Fore.RESET}")
    click.echo(f"\n{Fore.CYAN}Cara dapetin token:{Fore.RESET}")
    click.echo(f"  1. Buka {Fore.GREEN}stake.mba{Fore.RESET} di Kiwi Browser")
    click.echo(f"  2. Login, pencet {Fore.YELLOW}3 titik → Developer Tools{Fore.RESET}")
    click.echo(f"  3. Tab {Fore.YELLOW}Network{Fore.RESET}, filter: {Fore.GREEN}graphql{Fore.RESET}")
    click.echo(f"  4. Klik salah satu request, cari {Fore.YELLOW}x-access-token{Fore.RESET}")
    click.echo(f"  5. Copy value-nya ke sini: {Fore.WHITE}python main.py auth{Fore.RESET}")


# ── Click Group ──

@click.group(invoke_without_command=False)
@click.option("--proxy", default=None, help="Proxy URL (contoh: http://127.0.0.1:8080)")
@click.pass_context
def cli(ctx, proxy):
    """StakeBot — Taraje Compatible. 🎲 Dice 🚀 Limbo"""
    ctx.ensure_object(dict)
    ctx.obj["proxy"] = proxy


# ── Auth ──

@cli.command()
def auth():
    """🔑 Setup: pilih mirror → paste token → simpan."""
    click.echo(f"\n{Fore.CYAN}╔══════════════════════════════════════╗")
    click.echo(f"║  {Fore.YELLOW}Setup StakeBot — Pilih Mirror{Fore.CYAN}          ║")
    click.echo(f"╚══════════════════════════════════════╝{Fore.RESET}")

    mirror_options = ["auto (cari sendiri)", "stake.mba", "stake.com", "playstake.club", "custom (input URL)"]
    click.echo(f"\n{Fore.YELLOW}🌐 Pilih mirror:{Fore.RESET}")
    for i, opt in enumerate(mirror_options, 1):
        click.echo(f"  {i}. {opt}")
    mc = click.prompt("  Pilihan", type=int, default=1)
    idx = min(max(mc, 1), len(mirror_options))
    sel = mirror_options[idx - 1]

    if sel == "auto (cari sendiri)":
        mirror_val, mirror_mode, base_url = "auto", True, "https://stake.com"
    elif sel == "custom (input URL)":
        mirror_val = click.prompt("  URL mirror")
        mirror_mode, base_url = False, f"https://{mirror_val}" if not mirror_val.startswith("http") else mirror_val
    else:
        mirror_val, mirror_mode, base_url = sel, False, f"https://{sel}"

    click.echo(f"  → {Fore.GREEN}Mirror: {mirror_val}{Fore.RESET}")
    click.echo(f"\n{Fore.YELLOW}🔑 Paste x-access-token (dari DevTools → Network → graphql → headers):{Fore.RESET}")
    token = click.prompt(f"  Token", hide_input=True)

    cfg = StakeConfig(access_token=token, mirror_mode=mirror_mode, base_url=base_url)
    StakeConfigManager.save(cfg)
    click.echo(f"{Fore.GREEN}  ✅ Config disimpan!{Fore.RESET}")
    click.echo(f"\n  Jalankan: {Fore.WHITE}python main.py balance{Fore.RESET}  → cek saldo")
    click.echo(f"             {Fore.WHITE}python main.py run{Fore.RESET}      → main interaktif")


@cli.command()
def curl():
    """🔗 Setup dari cURL command — paling gampang!"""
    click.echo(f"\n{Fore.CYAN}╔══════════════════════════════════════╗")
    click.echo(f"║  {Fore.YELLOW}Setup dari cURL command{Fore.CYAN}              ║")
    click.echo(f"╚══════════════════════════════════════╝{Fore.RESET}")
    click.echo(f"")
    click.echo(f"{Fore.YELLOW}Cara dapetin cURL:{Fore.RESET}")
    click.echo(f"  1. Buka {Fore.GREEN}stake.mba{Fore.RESET} di Kiwi Browser & login")
    click.echo(f"  2. Buka Developer Tools → Network tab")
    click.echo(f"  3. Filter: {Fore.GREEN}graphql{Fore.RESET}")
    click.echo(f"  4. {Fore.YELLOW}RIGHT CLICK{Fore.RESET} → salah satu request /_api/graphql")
    click.echo(f"  5. Pilih: {Fore.GREEN}Copy → Copy as cURL{Fore.RESET}")
    click.echo(f"  6. Paste di sini:\n")

    curl_text = click.prompt(f"  Paste cURL command", hide_input=False)

    from core.client import parse_curl
    parsed = parse_curl(curl_text)

    if not parsed.get("access_token"):
        click.echo(f"{Fore.RED}  ❌ Gagal: x-access-token tidak ditemukan di cURL.{Fore.RESET}")
        click.echo(f"     Pastikan kamu copy dari request /_api/graphql (bukan request lain)")
        return

    token = parsed["access_token"]
    cookie = parsed.get("cookie", "")
    url = parsed.get("url", "")

    # Extract mirror URL from the request URL
    mirror_url = "https://stake.com"
    if url:
        for m in KNOWN_MIRRORS:
            if m in url:
                mirror_url = m
                break

    click.echo(f"  {Fore.GREEN}✅ Token berhasil diextract!{Fore.RESET}")
    click.echo(f"     Token: {token[:15]}...{token[-5:]}")
    if cookie:
        click.echo(f"     Cookie: ada ({len(cookie)} chars)")
    click.echo(f"     Mirror: {mirror_url}")

    cfg = StakeConfig(access_token=token, session_cookie=cookie,
                      base_url=mirror_url, mirror_mode=True)
    StakeConfigManager.save(cfg)
    click.echo(f"{Fore.GREEN}  ✅ Config disimpan!{Fore.RESET}")
    click.echo(f"\n  Jalankan: {Fore.WHITE}python main.py balance{Fore.RESET}  → cek saldo")
    click.echo(f"             {Fore.WHITE}python main.py run{Fore.RESET}      → main interaktif")


# ── Diagnostic ──

@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def test(mirror):
    """🔍 Diagnostik koneksi — cek tiap mirror satu per satu."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)

    async def _run():
        click.echo(f"\n{Fore.CYAN}🔍 Diagnostik Koneksi Stake{Fore.RESET}")
        click.echo(f"  Token: {cfg.access_token[:10]}...{cfg.access_token[-4:]}")
        click.echo(f"  Mirror mode: {cfg.mirror_mode}")
        click.echo(f"  Base URL: {cfg.base_url}")
        click.echo("")

        from core.client import KNOWN_MIRRORS
        test_urls = [cfg.base_url] + [m for m in KNOWN_MIRRORS if m != cfg.base_url]

        async with StakeClient(cfg) as client:
            for url in test_urls:
                try:
                    api_url = url.rstrip("/") + "/_api/graphql"
                    click.echo(f"  {Fore.YELLOW}Coba {url}...{Fore.RESET}", nl=False)
                    user = await client.get_user_info()
                    if user:
                        click.echo(f"  {Fore.GREEN}✅ Berhasil! User: {user['name']}{Fore.RESET}")
                        click.echo(f"  {Fore.GREEN}   ✅ Mirror ini WORK!{Fore.RESET}")
                        click.echo(f"\n  {Fore.CYAN}Simpan config ini biar permanent:{Fore.RESET}")
                        click.echo(f"  {Fore.WHITE}  python main.py auth{Fore.RESET}")
                        return
                    else:
                        click.echo(f"  {Fore.RED}❌ Gagal (response kosong){Fore.RESET}")
                except Exception as e:
                    click.echo(f"  {Fore.RED}❌ {str(e)[:60]}{Fore.RESET}")

            click.echo(f"\n{Fore.RED}❌ Semua mirror gagal. Mungkin provider blokir semua.{Fore.RESET}")
            click.echo(f"   Coba: {Fore.YELLOW}1. VPN{Fore.RESET}  atau  {Fore.YELLOW}2. Proxy{Fore.RESET}")

    asyncio.run(_run())


# ── Balance ──

@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def balance(mirror):
    """💰 Tampilkan saldo."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)

    async def _run():
        click.echo(BANNER)
        try:
            async with StakeClient(cfg) as client:
                user = await client.get_user_info()
                if user:
                    click.echo(f"{Fore.GREEN}👤 {user['name']}{Fore.RESET}  {Fore.YELLOW}Level {user['level']}{Fore.RESET}  {Fore.CYAN}KYC Tier {user['kyc']}{Fore.RESET}")
                else:
                    click.echo(f"{Fore.RED}❌ Gagal ambil data user.{Fore.RESET}")
                    click.echo(f"   Jalankan: {Fore.YELLOW}python main.py test{Fore.RESET}  buat diagnosa")
                    return

                bal = await client.get_balance_simple()
                if "error" in bal:
                    click.echo(f"{Fore.RED}❌ {bal['error']}{Fore.RESET}")
                    return

                rates = await client._fetch_crypto_rates()
                click.echo(f"\n{Fore.WHITE}💰 Saldo:{Fore.RESET}")
                any_b = False
                for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                    if a > 0:
                        any_b = True
                        rate = rates.get(c, 0)
                        if rate > 0:
                            click.echo(f"  {c.upper():>6}  {Fore.CYAN}{a:<16.8f}{Fore.RESET} ≈ Rp {a*rate:,.0f}")
                        else:
                            click.echo(f"  {c.upper():>6}  {Fore.CYAN}{a:<16.8f}{Fore.RESET}")
                if not any_b:
                    click.echo(f"  {Fore.YELLOW}(semua kosong){Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}❌ Error: {e}{Fore.RESET}")
            click.echo(f"   Jalankan: {Fore.YELLOW}python main.py test{Fore.RESET}  buat diagnosa")

    asyncio.run(_run())


@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def info(mirror):
    """ℹ️  Info akun."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)

    async def _run():
        try:
            async with StakeClient(cfg) as client:
                user = await client.get_user_info()
                if not user:
                    click.echo(f"{Fore.RED}❌ Gagal{Fore.RESET}")
                    return
                click.echo(f"\n{Fore.GREEN}👤 {user['name']}{Fore.RESET}  {Fore.YELLOW}Level {user['level']}{Fore.RESET}  {Fore.CYAN}KYC T{user['kyc']}{Fore.RESET}")
                bal = await client.get_balance_simple()
                if "error" not in bal:
                    for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                        if a > 0:
                            click.echo(f"  {Fore.CYAN}{c.upper()}: {a:.8f}{Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}❌ {e}{Fore.RESET}")

    asyncio.run(_run())


# ── Interactive Run ──

async def _interactive_run(cfg):
    """Interactive setup like Taraje."""
    click.echo(BANNER)

    game = _pick("🎮 Pilih game:", ["Dice 🎲", "Limbo 🚀"])
    game_type = "limbo" if "Limbo" in game else "dice"

    coin = _pick("🪙 Pilih coin:", ["BTC", "ETH", "USDT", "LTC", "SOL", "DOGE", "TRX", "BNB", "XRP", "ADA", "Lainnya..."])
    if coin == "Lainnya...":
        coin = click.prompt("  Ketik kode coin", default="DOT").upper()

    base_bet = click.prompt(f"  💰 Base bet ({coin})", type=float,
                            default=0.001 if coin == "LTC" else (0.00001 if coin in ("USDT", "USDC") else (1 if coin in ("TRX", "DOGE") else 0.00000001)),
                            show_default=True)

    use_script = click.confirm("📜 Pakai LUA script?", default=True)
    script_path = None
    if use_script:
        scripts = sorted(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            snames = [s.stem for s in scripts]
            chosen = _pick("  Pilih strategi:", snames, default=0)
            script_path = SCRIPT_DIR / f"{chosen}.lua"

    if game_type == "dice":
        chance = click.prompt("  🎯 Target chance (%)", type=float, default=49.5, show_default=True)
        bethigh_opt = click.confirm("  ⬆️  Bet high?", default=True)
        target_val = chance
        over_val = bethigh_opt
    else:
        multiplier = click.prompt("  🎯 Target multiplier (x)", type=float, default=2.0, show_default=True)
        target_val = multiplier
        over_val = True

    max_bets, target_profit, target_loss = 0, 0.0, 0.0
    if click.confirm("⏹️  Atur stop condition?", default=False):
        max_bets = click.prompt("  Max bets (0=unlimited)", type=int, default=0)
        target_profit = click.prompt("  Stop profit (0=no limit)", type=float, default=0.0)
        target_loss = click.prompt("  Stop loss (0=no limit)", type=float, default=0.0)

    lua_engine = None
    if script_path:
        try:
            lua_engine = LuaScriptEngine(script_path.read_text())
            click.echo(f"{Fore.GREEN}  📜 {script_path.name}{Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}  ❌ LUA: {e}{Fore.RESET}")
            return

    bc = BetConfig(
        game_type=game_type, coin=coin.lower(), base_bet=base_bet,
        target=target_val, over=over_val,
        max_bets=max_bets, target_profit=target_profit, target_loss=target_loss,
    )

    if not click.confirm(f"\n  {Fore.YELLOW}Mulai sekarang?", default=True):
        click.echo(f"  {Fore.RED}Batal.{Fore.RESET}")
        return

    await _run_game(cfg, bc, lua_engine, game_type)


def _pick(prompt, options, default=0):
    """Show numbered options, return selected value."""
    click.echo(f"\n{Fore.CYAN}{prompt}{Fore.RESET}")
    for i, opt in enumerate(options, 1):
        m = f"{Fore.GREEN}▶{Fore.RESET}" if i-1 == default else " "
        click.echo(f"  {m} {i}. {opt}")
    choice = click.prompt(f"  (1-{len(options)})", type=int, default=default+1)
    return options[min(max(choice, 1), len(options)) - 1]


async def _run_game(cfg, bet_config, lua_engine=None, game_type=None):
    """Run betting session."""
    async with StakeClient(cfg) as client:
        # Try auth, but don't fail if it doesn't work - show diagnostics
        user = None
        try:
            user = await client.get_user_info()
        except:
            pass

        if not user:
            click.echo(f"\n{Fore.RED}❌ Gagal connect ke Stake.{Fore.RESET}")
            click.echo(f"  Penyebab: {Fore.YELLOW}1. Token expired  2. Domain diblokir  3. Koneksi error{Fore.RESET}")
            click.echo(f"  Coba: {Fore.WHITE}python main.py test{Fore.RESET}  buat diagnosa lengkap")
            click.echo(f"  Atau pake VPN/proxy biar koneksi lancar.")
            return

        # Show user info
        click.echo(f"\n{Fore.CYAN}▶️  {'='*36}")
        click.echo(f"  {Fore.GREEN}👤 {user['name']}{Fore.RESET}  Lv{user['level']}  KYC T{user['kyc']}")
        click.echo(f"  {'🎲' if bet_config.game_type=='dice' else '🚀'}{Fore.YELLOW} {bet_config.game_type.upper()}{Fore.RESET}  "
                   f"| {Fore.WHITE}{bet_config.coin.upper()}{Fore.RESET}  "
                   f"| Bet {Fore.CYAN}{bet_config.base_bet:.8f}{Fore.RESET}")
        click.echo(f"{Fore.CYAN}  {'='*36}{Fore.RESET}")

        bal = await client.get_balance_simple()
        cb = bal.get(bet_config.coin, 0)
        if cb <= 0:
            click.echo(f"{Fore.RED}⚠️  {bet_config.coin.upper()} = 0.{Fore.RESET}")
            others = [f"{c.upper()}: {a:.8f}" for c, a in sorted(bal.items(), key=lambda x: -x[1]) if a > 0]
            if others:
                click.echo(f"  Coin dengan saldo: {', '.join(others)}")
            return

        click.echo(f"  💰 {bet_config.coin.upper()}: {Fore.CYAN}{cb:.8f}{Fore.RESET}")
        click.echo(f"{Fore.YELLOW}  Ctrl+C buat stop{Fore.RESET}\n")

        async def on_bet(stats, result):
            out_icon = f"{Fore.GREEN}✅" if result.get("won") else f"{Fore.RED}❌"
            if bet_config.game_type == "limbo":
                crash = result.get("crash_point", 0)
                click.echo(f"\r#{stats.bets_placed:>4} {out_icon} S{stats.current_streak:+d} P{stats.total_profit:+.8f} 💥{crash:.2f}x    ", nl=False)
            else:
                outcome_num = result.get("outcome", "?")
                click.echo(f"\r#{stats.bets_placed:>4} {out_icon} S{stats.current_streak:+d} P{stats.total_profit:+.8f} 🎲{outcome_num}    ", nl=False)

        engine = BettingEngine(
            client=client, config=bet_config, lua_engine=lua_engine,
            on_bet_placed=on_bet,
            on_error=lambda m: click.echo(f"\n{Fore.RED}⚠️ {m}{Fore.RESET}"),
        )

        try:
            final_stats = await engine.run()
        except KeyboardInterrupt:
            engine._running = False
            final_stats = engine.stats

        click.echo(f"\n\n{Fore.CYAN}  {'='*36}")
        click.echo(f"  {Fore.WHITE}HASIL{Fore.RESET}")
        click.echo(f"  Bets: {final_stats.bets_placed}  ✅{final_stats.wins} ❌{final_stats.losses}")
        click.echo(f"  Profit: {Fore.GREEN if final_stats.total_profit>=0 else Fore.RED}{final_stats.total_profit:+.8f}{Fore.RESET}")
        click.echo(f"  Largest bet: {final_stats.largest_bet:.8f}")
        click.echo(f"{Fore.CYAN}  {'='*36}{Fore.RESET}")


# ── Commands ──

@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def run(mirror):
    """🎮 Mode interaktif — pilih game, coin, script, jalan."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)
    asyncio.run(_interactive_run(cfg))


@cli.command()
@click.option("--coin", "-c", default=None)
@click.option("--script", "-s", type=click.Path(exists=True), default=None)
@click.option("--base-bet", "-b", type=float, default=None)
@click.option("--chance", type=float, default=None)
@click.option("--high", is_flag=True, default=None)
@click.option("--max-bets", "-n", type=int, default=None)
@click.option("--target-profit", type=float, default=None)
@click.option("--target-loss", type=float, default=None)
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def dice(coin, script, base_bet, chance, high, max_bets, target_profit, target_loss, mirror):
    """🎲 Dice — kalo gak diisi, pake interaktif."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)
    if not coin or not base_bet:
        asyncio.run(_interactive_run(cfg))
        return
    lua = LuaScriptEngine(Path(script).read_text()) if script else None
    asyncio.run(_run_game(cfg, BetConfig(
        game_type="dice", coin=coin.lower(), base_bet=base_bet,
        target=chance or 49.5, over=high or True,
        max_bets=max_bets or 0, target_profit=target_profit or 0, target_loss=target_loss or 0,
    ), lua, "dice"))


@cli.command()
@click.option("--coin", "-c", default=None)
@click.option("--script", "-s", type=click.Path(exists=True), default=None)
@click.option("--base-bet", "-b", type=float, default=None)
@click.option("--multiplier", type=float, default=None)
@click.option("--max-bets", "-n", type=int, default=None)
@click.option("--target-profit", type=float, default=None)
@click.option("--target-loss", type=float, default=None)
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def limbo(coin, script, base_bet, multiplier, max_bets, target_profit, target_loss, mirror):
    """🚀 Limbo — kalo gak diisi, pake interaktif."""
    cfg = load_cfg()
    if not cfg.access_token:
        msg_no_token()
        return
    apply_mirror(cfg, mirror)
    if not coin or not base_bet:
        asyncio.run(_interactive_run(cfg))
        return
    lua = LuaScriptEngine(Path(script).read_text()) if script else None
    asyncio.run(_run_game(cfg, BetConfig(
        game_type="limbo", coin=coin.lower(), base_bet=base_bet,
        target=multiplier or 2.0, over=True,
        max_bets=max_bets or 0, target_profit=target_profit or 0, target_loss=target_loss or 0,
    ), lua, "limbo"))


# ── Main ──

def main():
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "run"]
    cli()


if __name__ == "__main__":
    main()
