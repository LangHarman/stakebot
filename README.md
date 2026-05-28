# 🎲 StakeBot — CLI Dice Bot untuk Stake.com

Bot CLI untuk auto-betting di Stake.com (mirror: playstake.club).
Support Termux (Android), VPS Linux, STB Armbian.

## Fitur

- **Manual Mode** — atur base bet, chance, on-win/on-loss strategy
- **LUA Script Mode** — compatible dengan Seuntjie DiceBot programmer mode
- **Mirror support** — otomatis pake playstake.club & mirror lainnya
- **Stop conditions** — max bets, target profit, max loss
- **Langsung real betting lewat API** — ga perlu browser
- **Cross-platform** — Termux ✅ VPS Linux ✅ Armbian ✅

## Instalasi

### Di Termux (Android)

```bash
pkg update && pkg upgrade
pkg install python python-pip git
pip install stakeapi lupa aiohttp websockets python-dotenv

git clone https://github.com/your/stakebot /sdcard/stakebot
cd /sdcard/stakebot
```

### Di VPS / Armbian

```bash
pip install stakeapi lupa aiohttp websockets python-dotenv
git clone <this-repo> ~/stakebot
cd ~/stakebot
```

## Setup: Dapetin Access Token

```bash
python main.py auth
```

Ini bakal munculin panduan:
1. Login ke Stake.com di Chrome/Firefox
2. F12 → Network → cari request `/_api/graphql`
3. Copy `x-access-token` header (96 karakter hex)
4. Paste ke terminal

Token disimpan otomatis di `~/.stakebot/config.json`

> ⚠️ Token expired kalo logout. Pas kena error auth, ulangi langkah di atas.

## Cara Pakai

### Cek Balance

```bash
python main.py balance
```

### Manual Mode (interaktif)

```bash
python main.py manual
```

Nanti muncul wizard:
```
  Base bet (BTC) [0.000001]:
  Chance (%) [49.5]:
  Direction: 1. High / 2. Low
  On Win: 1. Reset / 2. Increase / 3. Same
  On Loss: 1. Reset / 2. Increase
  Stop conditions...
```

### LUA Script Mode

```bash
# Pake script bawaan
python main.py script martingale
python main.py script oscars_grind --max-bets 100

# Pake script custom
python main.py script /path/to/strategi.lua

# Generate template
python main.py gen-script custom -o strategi.lua
```

### Lihat daftar script

```bash
python main.py scripts
```

## LUA Script API (Seuntjie Compatible)

Script kamu harus punya fungsi `dobet()` yang dipanggil setelah setiap hasil bet.

### Variable yang bisa dipake:

| Variable | Access | Deskripsi |
|---|---|---|
| `balance` | RO | Saldo saat ini |
| `profit` | RO | Profit/loss total |
| `wins` | RO | Total menang |
| `losses` | RO | Total kalah |
| `total_bets` | RO | Total bet |
| `current_streak` | RO | Streak saat ini (+/-) |
| `win` | RO | Boolean: menang/kalah |
| `previousbet` | RO | Jumlah bet sebelumnya |
| `crash` | RO | ⭐ Limbo: crash multiplier terakhir |
| `lastBet` | RO | Table: amount, payout, multiplier, won, crash_point, target_multiplier |
| `nextbet` | RW | ⭐ Jumlah bet selanjutnya |
| `chance` | RW | Chance % (0-98) |
| `high` | RW | Boolean: bet high/low (Dice) |
| `target_multiplier` | RW | ⭐ Target multiplier (set di top utk Limbo) |
| `basebet` | RW | Base bet (set di top-level) |
| `bethigh` | RW | Boolean: high/low (set di top-level) |

### Fungsi:

| Fungsi | Deskripsi |
|---|---|
| `stop()` | Hentikan bot |
| `print(...)` | Print debug ke console |
| `debug(...)` | Sama kayak print |

### Contoh Script

```lua
-- Martingale
basebet = 0.000001
bethigh = true
chance = 49.5

function dobet()
    if win then
        nextbet = basebet
    else
        nextbet = previousbet * 2
    end
end
```

## Dengan Mirror

Otomatis pake mirror kalo `--mirror auto` (default).

```bash
# Pake mirror explicit
python main.py manual --mirror auto
python main.py script martingale -m auto
```

## Struktur Proyek

```
stakebot/
├── main.py            ← CLI entry point
├── core/
│   ├── client.py      ← Stake API wrapper (auth, mirror, GraphQL)
│   └── engine.py      ← Betting engine (loop, stats, stop conditions)
├── modes/
│   ├── manual.py      ← Manual betting mode
│   └── script.py      ← LUA script mode (Seuntjie compatible)
├── scripts/           ← Contoh LUA scripts
│   ├── martingale.lua
│   ├── reverse_martingale.lua
│   ├── dalembert.lua
│   └── oscars_grind.lua
├── config.yaml        ← Config placeholder
└── README.md
```

## Disclaimer

⚠️ **Bot ini untuk edukasi.**
- Melanggar ToS Stake.com — akun bisa kena ban
- Judi resiko tinggi — jangan pake uang kebutuhan
- Saya (Melky) cuma bantu coding, resiko ditanggung user
