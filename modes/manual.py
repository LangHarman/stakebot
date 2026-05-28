"""
Manual betting mode - user configures bet parameters, bot executes.
Supports Dice and Limbo games.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.client import StakeClient, StakeConfig
from core.engine import BettingEngine, BetConfig, StopConditions


def get_manual_config():
    """Interactive config for manual mode."""
    print("\n" + "=" * 55)
    print("  🎲 STAKE BOT — MANUAL MODE")
    print("=" * 55)

    # Game selection
    print("\n  Game:")
    print("    1. 🎲 Dice")
    print("    2. 🚀 Limbo")
    game = input("  Choose [1]: ").strip() or "1"
    game_type = "limbo" if game == "2" else "dice"

    # Base bet
    while True:
        try:
            base = float(input("  Base bet (BTC) [0.000001]: ") or "0.000001")
            if base <= 0:
                print("  [!] Must be > 0")
                continue
            break
        except ValueError:
            print("  [!] Invalid number")

    if game_type == "dice":
        # Chance
        while True:
            try:
                chance = float(input("  Chance (%) [49.5]: ") or "49.5")
                if chance <= 0 or chance > 98:
                    print("  [!] Must be between 0.1 and 98.0")
                    continue
                break
            except ValueError:
                print("  [!] Invalid number")

        # Direction
        print("  Direction:")
        print("    1. High (bet over target)")
        print("    2. Low (bet under target)")
        direction = input("  Choose [1]: ").strip() or "1"
        bet_high = direction == "1"

        cfg = BetConfig(
            game_type="dice",
            base_bet=base,
            chance=chance,
            bet_high=bet_high,
        )
        param_label = f"{chance}% (target: {cfg.get_target()})"
        dir_label = "High ↑" if bet_high else "Low ↓"

    else:  # limbo
        while True:
            try:
                target_mult = float(input("  Target multiplier [2.0]: ") or "2.0")
                if target_mult < 1.01:
                    print("  [!] Must be at least 1.01x")
                    continue
                break
            except ValueError:
                print("  [!] Invalid number")

        cfg = BetConfig(
            game_type="limbo",
            base_bet=base,
            target_multiplier=target_mult,
        )
        param_label = f"{target_mult}x"
        dir_label = "N/A"

    # On win
    print("\n  On Win:")
    print("    1. Reset to base bet")
    print("    2. Increase bet")
    print("    3. Same bet")
    on_win = input("  Choose [1]: ").strip() or "1"

    # On loss
    print("  On Loss:")
    print("    1. Reset to base bet")
    print("    2. Increase bet")
    print("    3. Same bet")
    on_loss = input("  Choose [1]: ").strip() or "1"

    inc_pct = 0
    if on_win == "2" or on_loss == "2":
        while True:
            try:
                inc_pct = float(input("  Increase by (%) [100]: ") or "100")
                if inc_pct <= 0:
                    continue
                break
            except ValueError:
                print("  [!] Invalid number")

    on_win_map = {"1": "reset", "2": "increase", "3": "same"}
    on_loss_map = {"1": "reset", "2": "increase", "3": "same"}
    cfg.on_win = on_win_map.get(on_win, "reset")
    cfg.on_loss = on_loss_map.get(on_loss, "reset")
    cfg.increase_pct = inc_pct

    # Stop conditions
    print("\n  ── Stop Conditions (0 = no limit) ──")
    sc = StopConditions()
    try:
        sc.max_bets = int(input("  Max bets [0]: ") or "0")
    except ValueError:
        sc.max_bets = 0
    try:
        sc.target_profit = float(input("  Target profit (BTC) [0]: ") or "0")
    except ValueError:
        sc.target_profit = 0
    try:
        sc.max_loss = float(input("  Max loss (BTC) [0]: ") or "0")
    except ValueError:
        sc.max_loss = 0

    return cfg, sc, param_label, dir_label


async def run_manual(token: str, mirror: bool = False):
    """Run manual betting mode."""
    config = StakeConfig(access_token=token)
    if mirror:
        config.mirror_mode = True

    # Test auth
    print("\n🔄 Testing authentication...")
    async with StakeClient(config) as client:
        ok = await client.check_auth()
        if not ok:
            print("❌ Authentication failed! Check your access token.")
            print("   Run: python main.py auth")
            return
        print("✅ Authentication OK!")

        try:
            bal = await client.get_balance_simple()
            print(f"💰 Balance: {bal}")
        except Exception as e:
            print(f"  Warning: could not fetch balance: {e}")

    # Get config
    bet_cfg, stop_cfg, param_label, dir_label = get_manual_config()

    # Build engine with game-specific place_bet
    async with StakeClient(config) as client:
        if bet_cfg.game_type == "limbo":
            place_bet_fn = lambda amt, target_multiplier=None, **kw: client.place_limbo_bet(
                amount=amt, target_multiplier=target_multiplier
            )
        else:
            place_bet_fn = lambda amt, target=None, over=None, **kw: client.place_dice_bet(
                amount=amt, target=target, over=over
            )

        engine = BettingEngine(
            place_bet_fn=place_bet_fn,
            get_balance_fn=lambda: client.get_balance_simple(),
        )
        engine.config = bet_cfg
        engine.stop_conditions = stop_cfg

        print("\n" + "─" * 55)
        print("  📋 CONFIG SUMMARY")
        print("─" * 55)
        print(f"  Game:     {'🚀 Limbo' if bet_cfg.game_type == 'limbo' else '🎲 Dice'}")
        print(f"  Base bet: {bet_cfg.base_bet} BTC")
        print(f"  Params:   {param_label}")
        print(f"  Payout:   {bet_cfg.get_payout()}x")
        if bet_cfg.game_type == "dice":
            print(f"  Dir:      {dir_label}")
        print(f"  On Win:   {bet_cfg.on_win} ({bet_cfg.increase_pct}%)")
        print(f"  On Loss:  {bet_cfg.on_loss} ({bet_cfg.increase_pct}%)")
        print(f"  Max bets: {stop_cfg.max_bets or '∞'}")
        print(f"  Target:   {stop_cfg.target_profit or '∞'} BTC")
        print(f"  Max loss: {stop_cfg.max_loss or '∞'} BTC")
        print("─" * 55)
        input("\n  Press Enter to start betting (Ctrl+C to stop)...\n")

        await engine.run()
