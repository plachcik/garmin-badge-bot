# Garmin Badge Bot

A Telegram bot that notifies you about available Garmin Connect badges — weekly for challenges ending that week, and daily when there's a one-day-only badge available.

The bot is already live and running in Telegram — find it at [@GarminBadgeBot](https://t.me/GarminBadgeBot).

## Commands

| Command | Description |
|---|---|
| `/start` | Subscribe to scheduled badge notifications |
| `/subscribe` | Subscribe to scheduled badge notifications |
| `/dawaj_odznaki` | Subscribe to scheduled badge notifications |
| `/odznaki` | Check available badges right now |

To receive scheduled digests, anyone in the chat needs to send `/subscribe` or `/dawaj_odznaki` once. Works in both private chats and group chats.

---

## How to make this bot your own

If you want to run your own instance:

### 1. Clone the repo and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create a Telegram bot

Message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token.

### 3. Set environment variables

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `GARMIN_EMAIL` | Your Garmin Connect email |
| `GARMIN_PASSWORD` | Your Garmin Connect password |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot)) |

### 4. Run

```bash
python main.py
```

### 5. Deploy to Railway

Push to GitHub, create a Railway project linked to your repo, add the environment variables, and mount a volume at `/app/data` with `DATA_DIR=/app/data`.

#### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `.` | Directory for persistent files. Set to `/app/data` on Railway with a volume mounted there. |
| `DAILY_HOUR` | `8` | Hour (UTC) when scheduled checks run |
| `DAILY_MINUTE` | `0` | Minute when scheduled checks run |
| `WEEKLY_EVERY_DAY` | `false` | Set to `true` to run the weekly digest every day instead of Mondays only |

## Scheduled messages

### Weekly digest — every Monday at 8:00 UTC
(or every day when `WEEKLY_EVERY_DAY=true`)

Lists all badges whose end date falls within the current week:

```
👋🏻 Żeby nie umknęło!

Dostępne odznaki w tym tygodniu:

• June Weekend 40K ⭐️⭐️
  🎯 (jedna aktywność)
  ⏰ Wyzwanie zaczyna się 12 czerwca a kończy 14 czerwca
```

### Today-special check — every day at 8:00 UTC

Fires only when there are badges whose start and end date share the same calendar day (e.g. `badgeStartDate: 2019-07-04`, `badgeEndDate: 2026-07-04` fires every July 4th). Silent if none are found.

```
Żeby nie umknęło 💡

📅 Dostępne odznaki tylko na dziś:

• Independence Run ⭐️
  🎯 5 km (łącznie)
  ⏰ Tylko dziś!!
```
