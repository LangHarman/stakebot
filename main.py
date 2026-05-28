#!/usr/bin/env python3
"""
🎲 StakeBot CLI — Automated betting bot untuk Stake.com

Fitur:
  • Manual mode — atur base bet, chance, on-win/on-loss strategy
  • LUA Script mode — compatible dengan Seuntjie DiceBot programmer mode
  • Mirror support — playstake.club dan mirror lainnya
  • Cross-platform — jalan di Termux (Android), VPS Linux, STB Armbian

Usage:
  python main.py auth            - Panduan dapetin access token
  python main.py manual          - Manual betting mode (interaktif)
  python main.py script [file]   - LUA script mode
  python main.py scripts         - Lihat daftar script contoh
  python main.py balance         - Cek balance akun
"""
import sys
import os
import asyncio
import argparse
from pathlib import Path

# Make sure we can find core/
sys.path.insert(0, os.path.dirname(__file__))

from core.client import (
    StakeClient, StakeConfig, StakeConfigManager,
    get_token_from_browser_instructions, test_auth,
)


# ── Global flag: use mirror ──
USE_MIRROR = False


def set_mirror_flag(mirror_str: str):
    """Parse mirror flag from command line."""
    global USE_MIRROR
    parts = mirror_str.split(",") if mirror_str else []
    if "auto" in parts or not parts:
        USE_MIRROR = True
        return "https://playstake.club"
    return "https://stake.com"


def get_token(args) -> str:
    """Get token from args, config file, or prompt."""
    if args.token:
        return args.token

    # Try config file
    cfg = StakeConfigManager.load()
    if cfg.access_token:
        return cfg.access_token

    # Prompt
    print("\n🔑 Enter your Stake.com access token:")
    token = input("  Token: ").strip()
    if token:
        # Save it
        cfg.access_token = token
        StakeConfigManager.save(cfg)
        print("✅ Token saved to ~/.stakebot/config.json")
    return token


# ── Commands ───────────────────────────────────────────

async def cmd_auth(args):
    """Show instructions for getting access token."""
    print(get_token_from_browser_instructions())
    token = input("\n  Paste token here to test (or Enter to skip): ").strip()
    if token:
        ok = await test_auth(token)
        if ok:
            print("✅ Token valid! Saving...")
            cfg = StakeConfig(access_token=token)
            StakeConfigManager.save(cfg)
        else:
            print("❌ Token invalid. Double-check the steps above.")
            print("   Make sure you're logged into Stake.com in your browser.")


async def cmd_balance(args):
    """Check account balance."""
    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return

    cfg = StakeConfig(access_token=token)
    if USE_MIRROR:
        cfg.mirror_mode = True

    async with StakeClient(cfg) as client:
        ok = await client.check_auth()
        if not ok:
            print("❌ Auth failed! Token invalid/expired.")
            return
        print("✅ Auth OK")
        try:
            bal = await client.get_balance_simple()
            print(f"\n💰 Balance: {bal}")
        except Exception as e:
            print(f"  Error fetching balance: {e}")


async def cmd_manual(args):
    """Run manual betting mode."""
    from modes.manual import run_manual

    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return

    await run_manual(token, mirror=USE_MIRROR)


async def cmd_script(args):
    """Run LUA script betting mode."""
    from modes.script import run_script, get_script_path

    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return

    script = args.script or "custom"
    max_bets = args.max_bets or 0
    await run_script(token, script, max_bets=max_bets, mirror=USE_MIRROR)


def cmd_scripts(args):
    """List available example scripts."""
    from modes.script import EXAMPLE_SCRIPTS

    base = os.path.dirname(__file__)
    scripts_dir = os.path.join(base, "scripts")
    
    print("\n📜  AVAILABLE SCRIPTS")
    print("=" * 50)
    print()
    
    # Built-in example scripts
    print("Built-in templates (can be used directly):")
    for name in EXAMPLE_SCRIPTS:
        desc = {
            "martingale": "Double on loss, reset on win (Dice)",
            "reverse_martingale": "Double on win, reset on loss (Dice)",
            "dalembert": "+1 unit on loss, -1 unit on win (Dice)",
            "oscars_grind": "Grind for small profits (Dice)",
            "limbo": "Target multiplier strategy (Limbo)",
            "custom": "Empty template — write your own!",
        }.get(name, "")
        print(f"  {name:20s} — {desc}")

    # Files in scripts/ directory
    if os.path.isdir(scripts_dir):
        files = sorted(f for f in os.listdir(scripts_dir) if f.endswith(".lua"))
        if files:
            print(f"\n  Scripts in {scripts_dir}/:")
            for f in files:
                fpath = os.path.join(scripts_dir, f)
                size = os.path.getsize(fpath)
                print(f"    {f:30s} ({size} bytes)")

    print()
    print("Usage:")
    print("  python main.py script martingale")
    print("  python main.py script oscars_grind --max-bets 100")
    print("  python main.py script /path/to/your/strategy.lua")


async def cmd_gen_script(args):
    """Generate an example script file."""
    from modes.script import EXAMPLE_SCRIPTS

    name = args.name or "custom"
    out_path = args.output or f"scripts/{name}.lua"

    if name not in EXAMPLE_SCRIPTS:
        print(f"❌ Unknown template: {name}")
        print(f"   Available: {', '.join(EXAMPLE_SCRIPTS.keys())}")
        return

    content = EXAMPLE_SCRIPTS[name]

    dir_path = os.path.dirname(out_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(out_path, "w") as f:
        f.write(content)

    print(f"✅ Generated {os.path.basename(out_path)} at {out_path}")
    print()
    print("Edit the file, then run:")
    print(f"  python main.py script {out_path}")


# ── Main ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🎲 StakeBot — Automated CLI betting bot for Stake.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py auth                 # Setup token
  python main.py manual               # Manual mode
  python main.py script martingale    # LUA script mode
  python main.py script oscars_grind --max-bets 50
  python main.py script myscript.lua  # Custom script
  python main.py gen-script custom -o myscript.lua
  python main.py balance --mirror auto
        """
    )
    parser.add_argument("--token", "-t", help="Access token (or save via 'auth')")
    parser.add_argument("--mirror", "-m", default="",
                        help='Mirror mode: "auto" or URL (default: auto)')

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # auth
    sub.add_parser("auth", help="Get/setup access token")

    # balance
    sub.add_parser("balance", help="Check account balance")

    # manual
    sub.add_parser("manual", help="Manual betting mode (interactive config)")

    # script
    sp = sub.add_parser("script", help="Run LUA script mode")
    sp.add_argument("script", nargs="?", default="custom",
                    help="Script name or path (default: custom)")
    sp.add_argument("--max-bets", type=int, default=0,
                    help="Stop after N bets (0 = unlimited)")

    # scripts
    sub.add_parser("scripts", help="List available scripts")

    # gen-script
    gs = sub.add_parser("gen-script", help="Generate example script file")
    gs.add_argument("name", nargs="?", default="custom",
                    choices=["martingale", "reverse_martingale", "dalembert",
                             "oscars_grind", "custom"],
                    help="Template name (default: custom)")
    gs.add_argument("--output", "-o", default="",
                    help="Output file path")

    args = parser.parse_args()

    # Mirror setup
    global USE_MIRROR
    mirror = args.mirror or os.environ.get("STAKE_MIRROR", "auto")
    if mirror and mirror != "none":
        USE_MIRROR = True
        print(f"🪞 Mirror mode: {mirror if mirror != 'auto' else 'auto'}")
        print()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "auth": cmd_auth,
        "balance": cmd_balance,
        "manual": cmd_manual,
        "script": cmd_script,
        "scripts": cmd_scripts,
        "gen-script": cmd_gen_script,
    }

    cmd = commands.get(args.command)
    if not cmd:
        parser.print_help()
        return

    # Sync or async
    if asyncio.iscoroutinefunction(cmd):
        asyncio.run(cmd(args))
    else:
        cmd(args)


if __name__ == "__main__":
    main()
