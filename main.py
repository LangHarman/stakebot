"""
StakeBot — CLI entry point.
Inspired by Taraje's CLI: Click-based, supports --stake.dice, --stake.limbo, --cfg etc.
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


def load_config(ctx, param, value):
    """Load LUA config file (like Taraje's --cfg)."""
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        click.echo(f"{Fore.RED}❌ Config file not found: {value}")
        ctx.exit(1)
    return path.read_text()


@click.group(invoke_without_command=True)
@click.option("--stake.dice", "game_dice", is_flag=True, help="Play Stake Dice")
@click.option("--stake.limbo", "game_limbo", is_flag=True, help="Play Stake Limbo")
@click.option("--cfg", "config_file", callback=load_config,
              type=click.Path(exists=True, readable=True),
              help="Path to LUA config file (Taraje-compatible)")
@click.option("--mirror", default="auto",
              type=click.Choice(["auto", "none", *[m.replace("https://", "") for m in KNOWN_MIRRORS]]),
              help="Mirror domain")
@click.option("--script", "-s", type=click.Path(exists=True), help="Path to LUA betting script")
@click.option("--api-key", "-k", help="Stake API key / access token")
@click.option("--manual", is_flag=True, help="Manual mode with config prompts")
@click.pass_context
def cli(ctx, game_dice, game_limbo, config_file, mirror, script, api_key, manual):
    """StakeBot — CLI betting bot for Stake.com (Dice & Limbo)."""
    ctx.ensure_object(dict)

    # Taraje-compatible: --stake.dice or --stake.limbo triggers betting
    game_type = "dice" if game_dice else ("limbo" if game_limbo else None)

    # Store in context
    ctx.obj["game_type"] = game_type
    ctx.obj["config_file"] = config_file
    ctx.obj["mirror"] = mirror
    ctx.obj["script"] = script
    ctx.obj["api_key"] = api_key
    ctx.obj["manual"] = manual

    # Track if a command was invoked
    ctx.obj["command_invoked"] = ctx.invoked_subcommand is not None


@cli.command()
def auth():
    """🔑 Authenticate: save access token."""
    token = click.prompt("x-access-token", hide_input=True)
    cfg = StakeConfig(access_token=token)
    StakeConfigManager.save(cfg)
    click.echo(f"{Fore.GREEN}✅ Token saved to {cfg.config_path}")


@cli.command()
@click.pass_context
def balance(ctx):
    """💰 Show balance in IDR."""
    asyncio.run(_cmd_balance(ctx.obj["mirror"]))


async def _cmd_balance(mirror: str):
    cfg = StakeConfigManager.load()
    if not cfg.access_token:
        click.echo(f"{Fore.RED}❌ No token. Run: stakebot auth")
        return

    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    click.echo(BANNER_COMPACT)
    async with StakeClient(cfg) as client:
        # Get user info
        user = await client.get_user_info()
        if user:
            click.echo(f"{Fore.GREEN}👤 {user['name']}  "
                       f"{Fore.YELLOW}Level {user['level']}  "
                       f"{Fore.CYAN}KYC Tier {user['kyc']}")
        else:
            click.echo(f"{Fore.RED}❌ Auth failed — token invalid")
            return

        # Get balance
        click.echo(f"{Fore.WHITE}💰 Balance:")
        idr_str = await client.get_balance_idr()
        click.echo(f"{Fore.CYAN}{idr_str}")


@cli.command()
@click.pass_context
def info(ctx):
    """ℹ️  Show account info (username, level, KYC)."""
    asyncio.run(_cmd_info(ctx.obj["mirror"]))


async def _cmd_info(mirror: str):
    cfg = StakeConfigManager.load()
    if not cfg.access_token:
        click.echo(f"{Fore.RED}❌ No token. Run: stakebot auth")
        return

    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    async with StakeClient(cfg) as client:
        user = await client.get_user_info()
        if user:
            click.echo(f"{Fore.GREEN}👤 Username: {user['name']}")
            click.echo(f"{Fore.YELLOW}📊 Level: {user['level']}")
            click.echo(f"{Fore.CYAN}🛡️  KYC Tier: {user['kyc']}")

            balances = await client.get_balance_simple()
            if "error" not in balances:
                click.echo(f"{Fore.WHITE}💰 Balances:")
                for coin, amt in sorted(balances.items(), key=lambda x: -x[1]):
                    if amt > 0:
                        click.echo(f"  {Fore.CYAN}{coin.upper()}: {amt:.8f}")
        else:
            click.echo(f"{Fore.RED}❌ Auth failed")


@cli.command()
@click.option("--coin", "-c", default="btc", help="Coin to use")
@click.option("--script", "-s", type=click.Path(exists=True), help="LUA betting script")
@click.option("--base-bet", "-b", type=float, default=0.00000001, help="Base bet amount")
@click.option("--chance", type=float, help="Target chance (dice) or multiplier (limbo)")
@click.option("--high", is_flag=True, help="Bet high (dice only)")
@click.option("--max-bets", "-n", type=int, default=0, help="Max number of bets")
@click.option("--target-profit", type=float, help="Stop when profit >= this")
@click.option("--target-loss", type=float, help="Stop when loss >= this")
@click.pass_context
def dice(ctx, coin, script, base_bet, chance, high, max_bets, target_profit, target_loss):
    """🎲 Play Stake Dice."""
    asyncio.run(_cmd_game(
        mirror=ctx.obj["mirror"],
        game_type="dice",
        coin=coin.lower(),
        script=script,
        base_bet=base_bet,
        chance=chance or 49.5,
        over=high,
        max_bets=max_bets,
        target_profit=target_profit,
        target_loss=target_loss,
    ))


@cli.command()
@click.option("--coin", "-c", default="btc", help="Coin to use")
@click.option("--script", "-s", type=click.Path(exists=True), help="LUA betting script")
@click.option("--base-bet", "-b", type=float, default=0.00000001, help="Base bet amount")
@click.option("--multiplier", type=float, default=2.0, help="Target multiplier")
@click.option("--max-bets", "-n", type=int, default=0, help="Max number of bets")
@click.option("--target-profit", type=float, help="Stop when profit >= this")
@click.option("--target-loss", type=float, help="Stop when loss >= this")
@click.pass_context
def limbo(ctx, coin, script, base_bet, multiplier, max_bets, target_profit, target_loss):
    """🚀 Play Stake Limbo."""
    asyncio.run(_cmd_game(
        mirror=ctx.obj["mirror"],
        game_type="limbo",
        coin=coin.lower(),
        script=script,
        base_bet=base_bet,
        chance=multiplier,
        over=True,
        max_bets=max_bets,
        target_profit=target_profit,
        target_loss=target_loss,
    ))


async def _cmd_game(mirror, game_type, coin, script, base_bet, chance, over,
                    max_bets, target_profit, target_loss):
    """Run a betting game."""
    cfg = StakeConfigManager.load()
    if not cfg.access_token:
        click.echo(f"{Fore.RED}❌ No token. Run: stakebot auth")
        return

    if mirror and mirror != "auto" and mirror != "none":
        cfg.base_url = f"https://{mirror}"
        cfg.mirror_mode = True
    elif mirror == "auto":
        cfg.mirror_mode = True

    # Load LUA script if provided
    lua_engine = None
    if script:
        try:
            script_content = Path(script).read_text()
            lua_engine = LuaScriptEngine(script_content)
            click.echo(f"{Fore.GREEN}📜 LUA script loaded: {script}")
        except Exception as e:
            click.echo(f"{Fore.RED}❌ LUA load error: {e}")
            return

    # Bet config
    bet_config = BetConfig(
        game_type=game_type,
        coin=coin,
        base_bet=base_bet,
        target=chance,
        over=over,
        max_bets=max_bets,
        target_profit=target_profit or 0,
        target_loss=target_loss or 0,
    )

    click.echo(BANNER)
    game_emoji = "🎲" if game_type == "dice" else "🚀"
    click.echo(f"{Fore.WHITE}{game_emoji} Playing Stake {game_type.upper()}  "
               f"|  Coin: {Fore.YELLOW}{coin.upper()}  "
               f"|  Base: {Fore.CYAN}{base_bet:.8f}")
    click.echo("")

    async with StakeClient(cfg) as client:
        # Verify auth
        user = await client.get_user_info()
        if not user:
            click.echo(f"{Fore.RED}❌ Auth failed — token invalid")
            return
        click.echo(f"{Fore.GREEN}👤 Logged in as: {user['name']}  "
                   f"Level {user['level']}  KYC Tier {user['kyc']}")

        # Show initial balance
        idr_balance = await client.get_balance_idr()
        click.echo(f"💰 Balance ({coin.upper()}):")
        click.echo(f"  {Fore.CYAN}{idr_balance}")

        balances = await client.get_balance_simple()
        coin_balance = balances.get(coin, 0)
        if coin_balance <= 0:
            click.echo(f"{Fore.RED}⚠️  {coin.upper()} balance is 0. "
                       f"Deposit first or choose a different coin."
                       f"\n  Available coins with balance:")
            for c, a in sorted(balances.items(), key=lambda x: -x[1]):
                if a > 0:
                    click.echo(f"  {Fore.YELLOW}{c.upper()}: {Fore.WHITE}{a:.8f}")
            return

        # Setup the engine
        async def on_bet(stats, result):
            outcome_icon = f"{Fore.GREEN}✅ WIN" if result.get("won") else f"{Fore.RED}❌ LOSE"
            if game_type == "limbo":
                crash = result.get("crash_point", 0)
                target_m = result.get("target_multiplier", chance)
                click.echo(
                    f"\r{stats.short_line()}  "
                    f"{outcome_icon}  "
                    f"🎯 {target_m:.2f}x  "
                    f"💥 {crash:.2f}x",
                    nl=False
                )
            else:
                outcome_num = result.get("outcome", "?")
                click.echo(
                    f"\r{stats.short_line()}  "
                    f"{outcome_icon}  "
                    f"🎯 {chance}  "
                    f"🎲 {outcome_num}",
                    nl=False
                )

        async def on_error(msg):
            click.echo(f"\n{Fore.RED}{msg}")

        engine = BettingEngine(
            client=client,
            config=bet_config,
            lua_engine=lua_engine,
            on_bet_placed=on_bet,
            on_error=on_error,
        )

        # Run!
        try:
            click.echo(f"\n{Fore.YELLOW}▶️  Starting... (Ctrl+C to stop)\n")
            final_stats = await engine.run()
        except KeyboardInterrupt:
            click.echo(f"\n\n{Fore.YELLOW}⏹️  Stopped by user")
            engine._running = False
            final_stats = engine.stats

        # Print final stats
        click.echo(f"\n\n{Fore.CYAN}═══════════════ FINAL STATS ═══════════════")
        click.echo(final_stats.summary())

        # Show IDR value
        idr_balance = await client.get_balance_idr()
        click.echo(f"💰 Balance now:\n{Fore.CYAN}{idr_balance}")


# ── Main entry point ──
def main():
    """Entry point for the stakebot CLI."""
    if len(sys.argv) == 1:
        # No args → show help
        sys.argv.append("--help")
    cli(obj={})


if __name__ == "__main__":
    main()
