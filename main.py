#!/usr/bin/env python3
"""
🎲 StakeBot CLI — Automated betting bot untuk Stake.com

Fitur:
  • Manual mode — atur base bet, chance, on-win/on-loss strategy
  • LUA Script mode — compatible dengan Seuntjie DiceBot programmer mode
  • Mirror support — auto fallback ke stake.mba, playstake.club, dll
  • Cross-platform — jalan di Termux (Android), VPS Linux, STB Armbian

Usage:
  python main.py auth                    # Setup token
  python main.py auth --mirror stake.mba # Setup token dari mirror
  python main.py manual                  # Manual mode
  python main.py balance                 # Cek balance
  python main.py script martingale       # LUA script mode
"""
import sys
import os
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from core.client import (
    StakeClient, StakeConfig, StakeConfigManager,
    KNOWN_MIRRORS,
    get_token_from_browser_instructions, test_auth,
    test_auth_from_config,
)


# ── Mirror resolver ────────────────────────────────────

def resolve_mirror(mirror_arg: str) -> dict:
    """
    Parse --mirror flag. Returns {mirror_mode, base_url}.
    
    --mirror auto      → mirror_mode=True, base_url from config or first mirror
    --mirror stake.mba → mirror_mode=True, base_url=https://stake.mba
    --mirror none      → mirror_mode=False, base_url=stake.com
    --mirror            → same as auto
    """
    arg = (mirror_arg or "auto").strip().lower()

    if arg == "none":
        return {"mirror_mode": False, "base_url": "https://stake.com"}

    if arg == "auto" or not arg:
        # Try to load saved config, use its base_url
        cfg = StakeConfigManager.load()
        return {
            "mirror_mode": True,
            "base_url": cfg.base_url or "https://stake.com",
        }

    # User specified a domain: "stake.mba", "playstake.club", etc.
    if not arg.startswith("http"):
        arg = "https://" + arg
    return {
        "mirror_mode": True,
        "base_url": arg.rstrip("/"),
    }


def get_token(args) -> str:
    """Get token from args, config file, or prompt."""
    if args.token:
        return args.token
    cfg = StakeConfigManager.load()
    if cfg.access_token:
        return cfg.access_token

    print("\n🔑 Enter your Stake.com access token:")
    token = input("  Token: ").strip()
    if token:
        cfg.access_token = token
        StakeConfigManager.save(cfg)
        print("✅ Token saved to ~/.stakebot/config.json")
    return token


def build_config(token: str, mirror_info: dict) -> StakeConfig:
    """Build StakeConfig from token + mirror info."""
    cfg = StakeConfigManager.load()
    cfg.access_token = token or cfg.access_token
    cfg.mirror_mode = mirror_info.get("mirror_mode", False)
    cfg.base_url = mirror_info.get("base_url", cfg.base_url)
    return cfg


# ── Commands ───────────────────────────────────────────

async def cmd_auth(args, mirror_info: dict):
    print(get_token_from_browser_instructions())
    token = input("\n  Paste token to test (or Enter to skip): ").strip()
    if not token:
        return

    cfg = build_config(token, mirror_info)

    print(f"  Testing with domain: {cfg.base_url}")
    if cfg.mirror_mode:
        print(f"  Mirror fallback enabled (auto fallback to mirrors)")

    ok = await test_auth_from_config(cfg)
    if ok:
        print(f"\n✅ Token valid! Domain: {cfg.base_url}")
        StakeConfigManager.save(cfg)
    else:
        print(f"\n❌ Auth failed on {cfg.base_url}")
        if not cfg.mirror_mode:
            print("   Coba lagi pake --mirror auto kalo pake mirror domain:")
            print("   python main.py auth --mirror auto")
        else:
            print("   Token mungkin expired. Ulangi dari Kiwi Browser.")
        # Still save so user can retry later
        StakeConfigManager.save(cfg)
        print("   Token tetap disimpan. Coba: python main.py balance")


async def cmd_balance(args, mirror_info: dict):
    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return

    cfg = build_config(token, mirror_info)
    async with StakeClient(cfg) as client:
        user_info = await client.get_user_info()
        if not user_info:
            print("❌ Auth failed! Token invalid/expired atau domain salah.")
            print(f"   Domain: {cfg.base_url}")
            print("   Coba: python main.py auth --mirror auto")
            return
        print(f"✅ Welcome, {user_info['name']}!")
        print(f"   Level: {user_info['level']}  |  KYC: Tier {user_info['kyc']}")
        print()

        # Show ALL balances
        print("💰  BALANCES")
        idr_str = await client.get_balance_idr()
        print(idr_str)


async def cmd_manual(args, mirror_info: dict):
    from modes.manual import run_manual
    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return
    cfg = build_config(token, mirror_info)
    await run_manual(cfg)


async def cmd_script(args, mirror_info: dict):
    from modes.script import run_script, get_script_path
    token = get_token(args)
    if not token:
        print("❌ No token. Run: python main.py auth")
        return
    cfg = build_config(token, mirror_info)
    script = args.script or "custom"
    max_bets = args.max_bets or 0
    await run_script(cfg, script, max_bets=max_bets)


def cmd_scripts(args):
    from modes.script import EXAMPLE_SCRIPTS
    base = os.path.dirname(__file__)
    scripts_dir = os.path.join(base, "scripts")

    print("\n📜  AVAILABLE SCRIPTS")
    print("=" * 50)
    print()

    print("Built-in templates:")
    for name in EXAMPLE_SCRIPTS:
        desc = {
            "martingale": "Double on loss, reset on win (Dice)",
            "reverse_martingale": "Double on win, reset on loss (Dice)",
            "dalembert": "+1 unit on loss, -1 unit on win (Dice)",
            "oscars_grind": "Grind for profits (Dice)",
            "limbo": "Multiplier target (Limbo)",
            "custom": "Empty template",
        }.get(name, "")
        print(f"  {name:20s} — {desc}")

    if os.path.isdir(scripts_dir):
        files = sorted(f for f in os.listdir(scripts_dir) if f.endswith(".lua"))
        if files:
            print(f"\n  Script files ({scripts_dir}/):")
            for f in files:
                fpath = os.path.join(scripts_dir, f)
                print(f"    {f:30s} ({os.path.getsize(fpath)} bytes)")

    print()
    print("Usage:")
    print("  python main.py script martingale")
    print("  python main.py script oscars_grind --max-bets 100")


async def cmd_gen_script(args):
    from modes.script import EXAMPLE_SCRIPTS
    name = args.name or "custom"
    out_path = args.output or f"scripts/{name}.lua"
    if name not in EXAMPLE_SCRIPTS:
        print(f"❌ Unknown: {name}")
        return
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(EXAMPLE_SCRIPTS[name])
    print(f"✅ Generated {os.path.basename(out_path)}")
    print(f"   python main.py script {out_path}")


# ── Main ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🎲 StakeBot — CLI betting bot untuk Stake.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py auth                      # Setup token
  python main.py auth --mirror stake.mba   # Token dari mirror
  python main.py balance                   # Cek balance
  python main.py balance --mirror auto     # Cek balance via mirror
  python main.py manual                    # Manual mode
  python main.py script martingale         # LUA script mode
  python main.py script limbo_martingale   # Limbo LUA script
        """
    )
    parser.add_argument("--token", "-t", help="Access token")
    parser.add_argument("--mirror", "-m", default="auto",
                        help='Mirror: "auto", "stake.mba", "playstake.club", "none"')

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("auth", help="Setup access token")
    sub.add_parser("balance", help="Check balance")
    sub.add_parser("manual", help="Manual betting mode")

    sp = sub.add_parser("script", help="LUA script mode")
    sp.add_argument("script", nargs="?", default="custom",
                    help="Script name or path (default: custom)")
    sp.add_argument("--max-bets", type=int, default=0,
                    help="Stop after N bets (0 = unlimited)")

    sub.add_parser("scripts", help="List available scripts")

    gs = sub.add_parser("gen-script", help="Generate example script")
    gs.add_argument("name", nargs="?", default="custom")
    gs.add_argument("--output", "-o", default="")

    args = parser.parse_args()

    # Resolve mirror
    mirror_info = resolve_mirror(args.mirror)
    if mirror_info["mirror_mode"]:
        print(f"🪞 Mirror: {mirror_info['base_url']}")
    print()

    if not args.command:
        parser.print_help()
        return

    # Dispatch
    cmds = {
        "auth": cmd_auth,
        "balance": cmd_balance,
        "manual": cmd_manual,
        "script": cmd_script,
        "scripts": cmd_scripts,
        "gen-script": cmd_gen_script,
    }

    cmd = cmds.get(args.command)
    if not cmd:
        parser.print_help()
        return

    if asyncio.iscoroutinefunction(cmd):
        asyncio.run(cmd(args, mirror_info))
    else:
        cmd(args)


if __name__ == "__main__":
    main()
