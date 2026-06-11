# Garmin Badge Bot

A Telegram bot that monitors your Garmin Connect badges and sends daily digests of newly earned badges, active weekly challenges, and one-day-only special badges.

## Setup

### 1. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the token it gives you

### 2. Get your Telegram chat ID

1. Start your bot (send it `/start`)
2. Message [@userinfobot](https://t.me/userinfobot) — it will reply with your chat ID

### 3. Configure environment

```bash
cp .env.example .env
# Fill in GARMIN_EMAIL, GARMIN_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

### 4. Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

### 5. Deploy to Railway

1. Push to a GitHub repo
2. Create a new Railway project and link it to GitHub
3. Add the environment variables below in Railway's Variables tab
4. Railway builds and runs the Dockerfile automatically

#### Required environment variables

| Variable | Description |
|---|---|
| `GARMIN_EMAIL` | Your Garmin Connect login email |
| `GARMIN_PASSWORD` | Your Garmin Connect password |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat/user ID |

#### Optional environment variables

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `.` | Directory for persistent files (`garmin_tokens.json`, `garmin_state.json`). Set to `/app/data` on Railway with a volume mounted there. |
| `DAILY_HOUR` | `8` | Hour (UTC) when scheduled checks run |
| `DAILY_MINUTE` | `0` | Minute when scheduled checks run |
| `WEEKLY_EVERY_DAY` | `false` | Set to `true` to run the weekly digest every day instead of Mondays only (useful for testing) |

## Commands

| Command | Description |
|---|---|
| `/start` | Show help and your chat ID |
| `/odznaki` | Manually trigger both the weekly digest and today-special check |

## Scheduled messages

### Weekly digest — every Monday at 8:00 UTC
(or every day when `WEEKLY_EVERY_DAY=true`)

Lists all badges whose end date falls within the current week:

```
👋🏻 Żeby nie umknęło!

Dostępne odznaki w tym tygodniu:

• June Weekend 40K ⭐️⭐️
  🎯 (jedna aktywność)
  ⏰ Zaczyna się 12 czerwca a kończy 14 czerwca
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

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest          # run tests
ruff check .    # lint
```

## Notes

- Garmin has no official public API — the bot logs in via a headless Firefox browser (Playwright) and keeps the session cookies in `garmin_tokens.json`
- State is stored in `garmin_state.json` to track which badges have already been reported
- On Railway, mount a volume at `/app/data` and set `DATA_DIR=/app/data` so tokens survive redeploys
