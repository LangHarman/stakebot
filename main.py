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

BANNER_COMPACT = f"""
{Fore.CYAN} ╭──────────────────────────────────╮
{Fore.CYAN} │{Fore.YELLOW}  StakeBot{Fore.WHITE} - {Fore.GREEN}Taraje Compatible{Fore.CYAN}  │
{Fore.CYAN} │{Fore.WHITE}  🎲 Dice  🚀 Limbo{Fore.CYAN}            │
{Fore.CYAN} ╰──────────────────────────────────╯{Fore.RESET}
"""

SCRIPT_DIR = Path(__file__).parent / "scripts"

# ── Helpers ──

def load_config_with_logging(path: Path, mirror_opt: str = "auto") -> StakeConfig:
    """Load config, print helpful message if missing."""
    cfg = StakeConfigManager.load()
    if not cfg.access_token:
        click.echo(f"\n{Fore.YELLOW}⚠️  Belum ada token! Jalankan dulu:{Fore.RESET}")
        click.echo(f"  {Fore.WHITE}python main.py auth --force{Fore.RESET}")
        click.echo(f"\n{Fore.CYAN}Cara dapetin token:{Fore.RESET}")
        click.echo(f"  1. Buka salah satu mirror di {Fore.YELLOW}Kiwi Browser{Fore.RESET}:")
        click.echo(f"     {Fore.GREEN}stake.mba{Fore.RESET} atau mirror lain yang bisa dibuka")
        click.echo(f"  2. Login, pencet {Fore.YELLOW}3 titik → Developer Tools{Fore.RESET}")
        click.echo(f"  3. Tab {Fore.YELLOW}Network{Fore.RESET}, filter: {Fore.GREEN}graphql{Fore.RESET}")
        click.echo(f"  4. Klik request /_api/graphql, cari {Fore.YELLOW}x-access-token{Fore.RESET} di headers")
        click.echo(f"  5. Copy value-nya, paste ke sini:\n")
        return None

    # Apply mirror settings
    if mirror_opt and mirror_opt != "auto" and mirror_opt != "none":
        cfg.base_url = f"https://{mirror_opt}"
        cfg.mirror_mode = False
    elif mirror_opt == "auto":
        cfg.mirror_mode = True

    return cfg


def print_bet_header(stats, config, user):
    """Print bet session info."""
    game_emoji = "🎲" if config.game_type == "dice" else "🚀"
    click.echo(f"\n{Fore.CYAN}▶️  {'═'*40}")
    click.echo(f"  {game_emoji} {Fore.YELLOW}{config.game_type.upper()}{Fore.RESET}  "
               f"| {Fore.WHITE}Coin:{Fore.CYAN} {config.coin.upper()}{Fore.RESET}  "
               f"| {Fore.WHITE}Bet:{Fore.CYAN} {config.base_bet:.8f}{Fore.RESET}")
    click.echo(f"  {Fore.GREEN}👤 {user['name']}{Fore.RESET}  "
               f"Lvl {user['level']}  KYC T{user['kyc']}")
    click.echo(f"{Fore.CYAN}  {'═'*40}{Fore.RESET}")
    click.echo(f"{Fore.YELLOW}  Ctrl+C kapan aja buat stop{Fore.RESET}")
    click.echo("")


# ── Auth ──

@click.group(invoke_without_command=False)
def cli():
    """StakeBot — Taraje Compatible. 🎲 Dice 🚀 Limbo"""
    pass


@cli.command()
def auth():
    """🔑 Setup: pilih mirror → paste token → simpan."""
    click.echo(f"\n{Fore.CYAN}╔══════════════════════════════════════╗")
    click.echo(f"║  {Fore.YELLOW}Setup StakeBot — Pilih Mirror dulu{Fore.CYAN}     ║")
    click.echo(f"╚══════════════════════════════════════╝{Fore.RESET}")

    # 1. Pilih mirror
    mirror_options = ["auto (cari sendiri)", "stake.mba", "stake.com", "playstake.club"]
    click.echo(f"\n{Fore.YELLOW}🌐 Pilih mirror domain:{Fore.RESET}")
    for i, opt in enumerate(mirror_options, 1):
        click.echo(f"  {i}. {opt}")
    mirror_choice = click.prompt("  Pilihan", type=int, default=1)
    mirror_map = {"auto": "auto", "stake.mba": "stake.mba", "stake.com": "stake.com", "playstake.club": "playstake.club"}
    idx = min(max(mirror_choice, 1), len(mirror_options))
    selected = mirror_options[idx - 1]
    if selected == mirror_options[0]:
        mirror_val = "auto"
    else:
        mirror_val = selected
    click.echo(f"  → {Fore.GREEN}{mirror_val}{Fore.RESET}")

    # 2. Minta token
    click.echo(f"\n{Fore.YELLOW}🔑 Sekarang paste x-access-token:{Fore.RESET}")
    click.echo(f"  {Fore.CYAN}(buka {mirror_val if mirror_val != 'auto' else 'mirror mana aja'} di Kiwi Browser → DevTools → cari x-access-token di headers){Fore.RESET}")
    token = click.prompt(f"  Token", hide_input=True)

    # 3. Simpan config
    cfg = StakeConfig(access_token=token, mirror_mode=(mirror_val == "auto"))
    if mirror_val != "auto":
        cfg.base_url = f"https://{mirror_val}"
    StakeConfigManager.save(cfg)
    click.echo(f"{Fore.GREEN}  ✅ Config disimpan!{Fore.RESET}")
    click.echo(f"\n{Fore.YELLOW}  Tes koneksi sebentar...{Fore.RESET}")

    # 4. Coba verifikasi
    async def _verify():
        try:
            async with StakeClient(cfg) as client:
                user = await client.get_user_info()
                if user:
                    click.echo(f"{Fore.GREEN}  ✅ Berhasil! Login sebagai:{Fore.RESET}")
                    click.echo(f"     👤 {user['name']}  Level {user['level']}  KYC Tier {user['kyc']}")
                    return True
        except:
            pass
        click.echo(f"{Fore.YELLOW}  ⚠️  Gagal verifikasi (token mungkin expired / koneksi error){Fore.RESET}")
        click.echo(f"     Config tetap tersimpan. Nanti coba: {Fore.WHITE}python main.py balance{Fore.RESET}")
        return False

    asyncio.run(_verify())
    click.echo(f"\n{Fore.GREEN}✅ Setup selesai! Sekarang tinggal main:{Fore.RESET}")
    click.echo(f"  {Fore.WHITE}python main.py{Fore.RESET}         → menu interaktif (pilih game, coin, script)")
    click.echo(f"  {Fore.WHITE}python main.py balance{Fore.RESET}  → lihat saldo")
    click.echo(f"  {Fore.WHITE}python main.py run{Fore.RESET}      → langsung main")


@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def balance(mirror):
    """💰 Tampilkan saldo."""
    cfg = load_config_with_logging(None, mirror)
    if not cfg:
        return
    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    async def _run():
        click.echo(BANNER_COMPACT)
        try:
            async with StakeClient(cfg) as client:
                user = await client.get_user_info()
                if not user:
                    click.echo(f"{Fore.RED}❌ Auth gagal — token mungkin expired.{Fore.RESET}")
                    click.echo(f"   Jalankan: {Fore.YELLOW}python main.py auth{Fore.RESET}")
                    return
                click.echo(f"{Fore.GREEN}👤 {user['name']}{Fore.RESET}  "
                           f"{Fore.YELLOW}Level {user['level']}{Fore.RESET}  "
                           f"{Fore.CYAN}KYC Tier {user['kyc']}{Fore.RESET}")
                click.echo(f"")
                # Show all balances with IDR
                bal = await client.get_balance_simple()
                if "error" in bal:
                    click.echo(f"{Fore.RED}❌ {bal['error']}{Fore.RESET}")
                    return
                rates = await client._fetch_crypto_rates()
                click.echo(f"{Fore.WHITE}💰 Saldo (semua coin):{Fore.RESET}")
                any_balance = False
                for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                    if a > 0:
                        any_balance = True
                        rate = rates.get(c, 0)
                        if rate > 0:
                            click.echo(f"  {c.upper():>6}  {Fore.CYAN}{a:<16.8f}{Fore.RESET} ≈ Rp {a*rate:,.0f}")
                        else:
                            click.echo(f"  {c.upper():>6}  {Fore.CYAN}{a:<16.8f}{Fore.RESET}")
                if not any_balance:
                    click.echo(f"  {Fore.YELLOW}(semua kosong){Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}❌ Error: {e}{Fore.RESET}")

    asyncio.run(_run())


@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def info(mirror):
    """ℹ️  Info akun (username, level, KYC)."""
    cfg = load_config_with_logging(None, mirror)
    if not cfg:
        return
    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    async def _run():
        try:
            async with StakeClient(cfg) as client:
                user = await client.get_user_info()
                if not user:
                    click.echo(f"{Fore.RED}❌ Gagal — token mungkin expired{Fore.RESET}")
                    return
                click.echo(f"\n{Fore.GREEN}👤 Username: {user['name']}{Fore.RESET}")
                click.echo(f"{Fore.YELLOW}📊 Level: {user['level']}{Fore.RESET}")
                click.echo(f"{Fore.CYAN}🛡️  KYC Tier: {user['kyc']}{Fore.RESET}")
                bal = await client.get_balance_simple()
                if "error" not in bal:
                    click.echo(f"{Fore.WHITE}💰 Coin dengan saldo:{Fore.RESET}")
                    for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                        if a > 0:
                            click.echo(f"  {Fore.CYAN}{c.upper()}: {a:.8f}{Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}❌ Error: {e}{Fore.RESET}")

    asyncio.run(_run())


# ── Interactive Mode (like Taraje's setup) ──

def _pick_option(prompt, options, default=0):
    """Show numbered options, return selected value."""
    click.echo(f"\n{Fore.CYAN}{prompt}{Fore.RESET}")
    for i, opt in enumerate(options, 1):
        marker = f"{Fore.GREEN}▶{Fore.RESET}" if i-1 == default else " "
        click.echo(f"  {marker} {i}. {opt}")
    choice = click.prompt(f"  Pilihan (1-{len(options)})", type=int, default=default+1)
    return options[min(max(choice, 1), len(options)) - 1]


async def _interactive_run(cfg):
    """Interactive setup like Taraje."""
    click.echo(BANNER)

    # 1. Pilih game
    game = _pick_option("🎮 Pilih game:", ["Dice 🎲", "Limbo 🚀"])
    game_type = "limbo" if "Limbo" in game else "dice"

    # 2. Pilih coin
    coin = _pick_option(
        "🪙 Pilih coin (BTC default, bisa ketik custom):",
        ["BTC", "ETH", "USDT", "LTC", "SOL", "DOGE", "TRX", "BNB", "XRP", "ADA", "Lainnya..."]
    )
    if coin == "Lainnya...":
        coin = click.prompt("  Ketik kode coin (contoh: DOT, MATIC, APT)", default="DOT").upper()

    # 3. Base bet
    base_bet = click.prompt(
        f"  💰 Base bet ({coin})",
        type=float,
        default=0.00001 if coin in ("USDT", "USDC") else (1 if coin in ("TRX", "DOGE") else 0.00001),
        show_default=True
    )

    # 4. Script or manual
    use_script = click.confirm(f"📜 Pakai LUA script?", default=True)
    script_path = None
    if use_script:
        scripts = list(SCRIPT_DIR.glob("*.lua"))
        if scripts:
            script_names = [s.stem for s in scripts]
            chosen = _pick_option("  Pilih strategi:", script_names, default=0)
            script_path = SCRIPT_DIR / f"{chosen}.lua"
        else:
            click.echo(f"{Fore.YELLOW}  Tidak ada script di scripts/{Fore.RESET}")
            use_script = False

    # 5. Chance/target
    if game_type == "dice":
        chance = click.prompt("  🎯 Target chance (%)", type=float, default=49.5, show_default=True)
        bethigh = click.confirm("  ⬆️  Bet high (over)?", default=True)
        click.echo(f"\n{Fore.GREEN}  ▶️  {game_type.upper()} | {coin} | {base_bet} | chance {chance}% | {'high' if bethigh else 'low'}{Fore.RESET}")
        target_val = chance
        over_val = bethigh
    else:
        multiplier = click.prompt("  🎯 Target multiplier (x)", type=float, default=2.0, show_default=True)
        click.echo(f"\n{Fore.GREEN}  ▶️  {game_type.upper()} | {coin} | {base_bet} | target {multiplier}x{Fore.RESET}")
        target_val = multiplier
        over_val = True

    # 6. Stop conditions
    max_bets = 0
    target_profit = 0.0
    target_loss = 0.0
    if click.confirm("⏹️  Atur stop condition?", default=False):
        max_bets = click.prompt("  Max bets (0 = unlimited)", type=int, default=0)
        target_profit = click.prompt("  Stop profit (0 = no limit)", type=float, default=0.0)
        target_loss = click.prompt("  Stop loss (0 = no limit)", type=float, default=0.0)

    # Confirm
    click.echo(f"\n{Fore.CYAN}  {'═'*35}")
    click.echo(f"  {Fore.WHITE}Game:{Fore.GREEN} {game_type.upper()}")
    click.echo(f"  {Fore.WHITE}Coin:{Fore.GREEN} {coin}")
    click.echo(f"  {Fore.WHITE}Base bet:{Fore.GREEN} {base_bet}")
    if script_path:
        click.echo(f"  {Fore.WHITE}Script:{Fore.GREEN} {script_path.name}")
    click.echo(f"  {Fore.CYAN}  {'═'*35}")
    confirm = click.confirm(f"\n  {Fore.YELLOW}Mulai sekarang?", default=True)
    if not confirm:
        click.echo(f"  {Fore.RED}Dibatalkan.{Fore.RESET}")
        return

    # Load LUA
    lua_engine = None
    if script_path:
        try:
            lua_engine = LuaScriptEngine(script_path.read_text())
            click.echo(f"{Fore.GREEN}  📜 Loaded: {script_path.name}{Fore.RESET}")
        except Exception as e:
            click.echo(f"{Fore.RED}  ❌ LUA error: {e}{Fore.RESET}")
            return

    bet_config = BetConfig(
        game_type=game_type,
        coin=coin.lower(),
        base_bet=base_bet,
        target=target_val,
        over=over_val,
        max_bets=max_bets,
        target_profit=target_profit,
        target_loss=target_loss,
    )

    await _run_game(cfg, bet_config, lua_engine)


async def _run_game(cfg, bet_config, lua_engine=None):
    """Run the betting game."""
    async with StakeClient(cfg) as client:
        user = await client.get_user_info()
        if not user:
            click.echo(f"{Fore.RED}❌ Auth gagal — token mungkin expired.{Fore.RESET}")
            click.echo(f"   Jalankan: {Fore.YELLOW}python main.py auth{Fore.RESET}")
            return
        print_bet_header(None, bet_config, user)

        bal = await client.get_balance_simple()
        coin_balance = bal.get(bet_config.coin, 0)
        if coin_balance <= 0:
            click.echo(f"{Fore.RED}⚠️  {bet_config.coin.upper()} balance = 0.{Fore.RESET}")
            # Show coins with balance
            click.echo(f"  Coin dengan saldo:")
            for c, a in sorted(bal.items(), key=lambda x: -x[1]):
                if a > 0:
                    click.echo(f"  {Fore.CYAN}{c.upper()}: {a:.8f}{Fore.RESET}")
            return

        click.echo(f"{Fore.CYAN}  Balance: {coin_balance:.8f} {bet_config.coin.upper()}{Fore.RESET}")

        async def on_bet(stats, result):
            game_icon = "🎲" if bet_config.game_type == "dice" else "🚀"
            out_icon = f"{Fore.GREEN}✅" if result.get("won") else f"{Fore.RED}❌"
            amount = result.get("amount", 0)

            if bet_config.game_type == "limbo":
                crash = result.get("crash_point", 0)
                tgt = result.get("target_multiplier", bet_config.target)
                click.echo(
                    f"\r{Fore.WHITE}#{stats.bets_placed:>4}{Fore.RESET} "
                    f"{out_icon}{Fore.RESET} "
                    f"S{stats.current_streak:+d} "
                    f"P{stats.total_profit:+.8f} "
                    f"💥{crash:.2f}x"
                    f"    ",
                    nl=False
                )
            else:
                outcome_num = result.get("outcome", "?")
                click.echo(
                    f"\r{Fore.WHITE}#{stats.bets_placed:>4}{Fore.RESET} "
                    f"{out_icon}{Fore.RESET} "
                    f"S{stats.current_streak:+d} "
                    f"P{stats.total_profit:+.8f} "
                    f"🎲{outcome_num}"
                    f"    ",
                    nl=False
                )

        async def on_error(msg):
            click.echo(f"\n{Fore.RED}  ⚠️  {msg}{Fore.RESET}")

        engine = BettingEngine(
            client=client,
            config=bet_config,
            lua_engine=lua_engine,
            on_bet_placed=on_bet,
            on_error=on_error,
        )

        try:
            final_stats = await engine.run()
        except KeyboardInterrupt:
            engine._running = False
            final_stats = engine.stats

        click.echo(f"\n\n{Fore.CYAN}  {'═'*35}")
        click.echo(f"  {Fore.WHITE}HASIL AKHIR{Fore.RESET}")
        click.echo(f"  {'═'*35}")
        click.echo(f"  Bets: {final_stats.bets_placed}")
        click.echo(f"  ✅ Wins: {final_stats.wins}  ❌ Losses: {final_stats.losses}")
        click.echo(f"  📊 Streak: {final_stats.current_streak:+d}")
        click.echo(f"  💰 Profit: {final_stats.total_profit:+.8f}")
        click.echo(f"  🏆 Largest: {final_stats.largest_bet:.8f}")
        click.echo(f"  {'═'*35}{Fore.RESET}")


# ── Commands ──

@cli.command()
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def run(mirror):
    """🎮 Mode interaktif (kayak Taraje) — pilih game, coin, script."""
    cfg = load_config_with_logging(None, mirror)
    if not cfg:
        return
    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True
    asyncio.run(_interactive_run(cfg))


@cli.command()
@click.option("--coin", "-c", default=None, help="Coin")
@click.option("--script", "-s", type=click.Path(exists=True), default=None, help="LUA script")
@click.option("--base-bet", "-b", type=float, default=None)
@click.option("--chance", type=float, default=None)
@click.option("--high", is_flag=True, default=None)
@click.option("--max-bets", "-n", type=int, default=None)
@click.option("--target-profit", type=float, default=None)
@click.option("--target-loss", type=float, default=None)
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def dice(coin, script, base_bet, chance, high, max_bets, target_profit, target_loss, mirror):
    """🎲 Main Dice dengan parameter opsional (kalo gak diisi, pake interaktif)."""
    cfg = load_config_with_logging(None, mirror)
    if not cfg: return
    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    # Interactive if anything missing
    if not coin or not base_bet:
        asyncio.run(_interactive_run(cfg))
        return

    asyncio.run(_run_game(
        cfg,
        BetConfig(
            game_type="dice",
            coin=coin.lower(),
            base_bet=base_bet,
            target=chance or 49.5,
            over=high or True,
            max_bets=max_bets or 0,
            target_profit=target_profit or 0,
            target_loss=target_loss or 0,
        ),
        lua_engine=LuaScriptEngine(Path(script).read_text()) if script else None,
    ))


@cli.command()
@click.option("--coin", "-c", default=None, help="Coin")
@click.option("--script", "-s", type=click.Path(exists=True), default=None, help="LUA script")
@click.option("--base-bet", "-b", type=float, default=None)
@click.option("--multiplier", type=float, default=None)
@click.option("--max-bets", "-n", type=int, default=None)
@click.option("--target-profit", type=float, default=None)
@click.option("--target-loss", type=float, default=None)
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]))
def limbo(coin, script, base_bet, multiplier, max_bets, target_profit, target_loss, mirror):
    """🚀 Main Limbo dengan parameter opsional (interaktif kalo gak diisi)."""
    cfg = load_config_with_logging(None, mirror)
    if not cfg: return
    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    if not coin or not base_bet:
        asyncio.run(_interactive_run(cfg))
        return

    asyncio.run(_run_game(
        cfg,
        BetConfig(
            game_type="limbo",
            coin=coin.lower(),
            base_bet=base_bet,
            target=multiplier or 2.0,
            over=True,
            max_bets=max_bets or 0,
            target_profit=target_profit or 0,
            target_loss=target_loss or 0,
        ),
        lua_engine=LuaScriptEngine(Path(script).read_text()) if script else None,
    ))


# ── Main ──

def main():
    if len(sys.argv) == 1:
        # Default: run interactive
        sys.argv = [sys.argv[0], "run"]
    cli()


if __name__ == "__main__":
    main()
