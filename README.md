# StakeBot 🎲🚀

**Taraje-compatible CLI betting bot for Stake.com** — Dice & Limbo.

Dibangun dengan pure Python (aiohttp + lupa), no Rust/cryptography needed.

## FITUR

- 🎲 **Dice** & 🚀 **Limbo** — full support
- 💰 **Balance in IDR** — CoinGecko conversion rates
- 📜 **LUA Scripting** — Taraje/Seuntjie DiceBot compatible!
- 🔄 **Seed rotation** — provably fair (via LUA `resetseed()`)
- 🌐 **Mirror support** — auto fallback + WebSocket
- 👤 **User info** — username, level, KYC tier
- 🪙 **80+ coins** supported (BTC, ETH, USDT, LTC, DOGE, TRX, etc.)

## INSTALLASI

```bash
# Dependencies
pip install aiohttp lupa click colorama

# Clone
git clone https://github.com/LangHarman/stakebot
cd stakebot
```

## CARA PAKAI

### 1. Auth (simpan token)

```bash
python main.py auth
```
→ Masukkan `x-access-token` dari Kiwi Browser DevTools.

### 2. Lihat balance

```bash
python main.py balance
python main.py info
```

### 3. Lari bot

**Dengan LUA script:**
```bash
python main.py dice --script scripts/martingale.lua --coin btc --base-bet 0.00000001
python main.py limbo --script scripts/limbo_martingale.lua --coin trx --base-bet 0.1
```

**Custom params:**
```bash
python main.py dice --coin btc --base-bet 0.00001 --chance 49.5 --high
python main.py dice --coin ltc --base-bet 0.001 --chance 90 --target-profit 0.01
python main.py limbo --coin trx --base-bet 0.5 --multiplier 5 --target-profit 10
```

**With mirror:**
```bash
python main.py --mirror stake.mba dice --script scripts/martingale.lua
```

**Batch mode:**
```bash
python main.py dice --coin trx --script scripts/martingale.lua --max-bets 1000 --target-profit 1.0
```

## LUA VARIABLES

| Variable | Tipe | Akses | Deskripsi |
|----------|------|-------|-----------|
| `basebet` | float | RW | Base bet amount |
| `nextbet` | float | RW | Next bet amount |
| `currency` | string | RW | Coin (btc, trx, ltc, etc) |
| `bethigh` | bool | RW | Bet high (true) or low (false) |
| `chance` | float | RW | Win chance for Dice (e.g. 49.5) |
| `target` | float | RW | Target multiplier for Limbo |
| `maxbet` | float | RW | Max bet cap |
| `resetIfProfit` | float | RW | Reset when profit >= this |
| `resetIfLose` | float | RW | Reset when loss >= this |
| `balance` | float | RO | Current balance |
| `profit` | float | RO | Running profit/loss |
| `bets` | int | RO | Total bets placed |
| `wins` | int | RO | Total wins |
| `losses` | int | RO | Total losses |
| `currentstreak` | int | RO | Win/loss streak (+/−) |
| `win` | bool | RO | Last bet result |
| `previousbet` | float | RO | Last bet amount |
| `lastBet` | table | RO | Last bet details |
| `broker` | string | RO | Casino name ("stake") |

## LUA FUNCTIONS

| Function | Deskripsi |
|----------|-----------|
| `dobet()` | Called by engine before each bet |
| `stop()` | Stop the bot |
| `resetseed(seed)` | Rotate client seed |
| `round(num, precision)` | Round number |

## AVAILABLE COINS

BTC, ETH, USDT, USDC, LTC, DOGE, BCH, XRP, TRX, ADA, DOT, SOL, MATIC, AVAX, LINK, UNI, ATOM, NEAR, FTM, ALGO, APT, ARB, OP, SUI, INJ, SEI, TIA... (80+ coins total)

## BUG / FEATURE REQUEST

- [Open Issue](https://github.com/LangHarman/stakebot/issues)
- Telegram: [@batavian_jaker](https://t.me/batavian_jaker)
