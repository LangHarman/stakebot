"""
Manual betting mode — user configures bet parameters, bot executes.
Supports Dice and Limbo games with optional coin/currency selection.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.client import StakeClient, StakeConfig
from core.engine import BettingEngine, BetConfig, StopConditions


def select_coin() -> str:
    """Optional coin/currency selection (default: BTC)."""
    coins = StakeClient.CURRENCIES
    print("\n  Currency — enter number or type symbol directly:")
    # Show top 10 + indicator for more
    shown = coins[:10]
    for i, c in enumerate(shown, 1):
        print(f"    {i:2d}. {c.upper()}")
    print(f"    ... ({len(coins)} total, type any symbol)")
    choice = input("  Choose [1 - BTC]: ").strip()
    if not choice:
        return "btc"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(coins):
            return coins[idx]
    except ValueError:
        pass
    # User typed a symbol e.g. "sol", "pepe"
    return choice.lower().strip()


def format_amount(amount: float, currency: str, rates: dict = None) -> str:
    """Format amount with optional IDR conversion."""
    if rates is None:
        rates = {}
    rate = rates.get(currency.lower(), 0)

    if currency.lower() in ("btc", "eth", "bnb", "ltc"):
        crypto_part = f"{amount:.8f} {currency.upper()}"
    else:
        crypto_part = f"{amount:.4f} {currency.upper()}"

    if rate > 0:
        return f"{crypto_part} (Rp {amount * rate:,.0f})"
    return crypto_part


def get_manual_config(coin: str = "btc"):
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

    coin_upper = coin.upper()

    # Base bet
    while True:
        try:
            prompt = f"  Base bet ({coin_upper}) [0.000001]: "
            base = float(input(prompt) or "0.000001")
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
            currency=coin,
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
            currency=coin,
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
        sc.target_profit = float(input(f"  Target profit ({coin_upper}) [0]: ") or "0")
    except ValueError:
        sc.target_profit = 0
    try:
        sc.max_loss = float(input(f"  Max loss ({coin_upper}) [0]: ") or "0")
    except ValueError:
        sc.max_loss = 0

    return cfg, sc, param_label, dir_label, coin


async def run_manual(cfg):
    """Run manual betting mode with coin selection and IDR balance."""
    # Test auth
    print("\n🔄 Testing authentication...")
    async with StakeClient(cfg) as client:
        ok = await client.check_auth()
        if not ok:
            print("❌ Authentication failed! Check your access token.")
            print("   Run: python main.py auth")
            return
        print("✅ Authentication OK!")

        # Show full balance with IDR
        print("\n💰 BALANCE")
        idr_str = await client.get_balance_idr()
        print(idr_str)

    # Select coin (optional)
    coin = select_coin()
    print(f"\n  Using currency: {coin.upper()}")

    # Get bet config
    bet_cfg, stop_cfg, param_label, dir_label, _ = get_manual_config(coin)

    # Fetch IDR rates for display
    async with StakeClient(cfg) as client:
        rates = await client._fetch_crypto_rates()

    # Build engine with game-specific place_bet
    async with StakeClient(cfg) as client:
        if bet_cfg.game_type == "limbo":
            async def place_fn(amt, target_multiplier=None, **kw):
                return await client.place_limbo_bet(
                    amount=amt, target_multiplier=target_multiplier, currency=coin
                )
        else:
            async def place_fn(amt, target=None, over=None, **kw):
                return await client.place_dice_bet(
                    amount=amt, target=target, over=over, currency=coin
                )

        engine = BettingEngine(
            place_bet_fn=place_fn,
            get_balance_fn=lambda: client.get_balance_simple(),
        )
        engine.config = bet_cfg
        engine.stop_conditions = stop_cfg

        base_str = format_amount(bet_cfg.base_bet, coin, rates)
        target_str = format_amount(stop_cfg.target_profit, coin, rates) if stop_cfg.target_profit else "∞"
        loss_str = format_amount(stop_cfg.max_loss, coin, rates) if stop_cfg.max_loss else "∞"

        print("\n" + "─" * 55)
        print("  📋 CONFIG SUMMARY")
        print("─" * 55)
        print(f"  Game:     {'🚀 Limbo' if bet_cfg.game_type == 'limbo' else '🎲 Dice'}")
        print(f"  Currency: {coin.upper()}")
        print(f"  Base bet: {base_str}")
        print(f"  Params:   {param_label}")
        print(f"  Payout:   {bet_cfg.get_payout()}x")
        if bet_cfg.game_type == "dice":
            print(f"  Dir:      {dir_label}")
        print(f"  On Win:   {bet_cfg.on_win} ({bet_cfg.increase_pct}%)")
        print(f"  On Loss:  {bet_cfg.on_loss} ({bet_cfg.increase_pct}%)")
        print(f"  Max bets: {stop_cfg.max_bets or '∞'}")
        print(f"  Target:   {target_str}")
        print(f"  Max loss: {loss_str}")
        print("─" * 55)
        input("\n  Press Enter to start betting (Ctrl+C to stop)...\n")

        await engine.run()
