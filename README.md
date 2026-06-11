# Garmin Badge Bot

A Telegram bot that checks your Garmin Connect badges every day and sends you a digest of newly earned badges and active challenges.

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
2. Create a new Railway project → Deploy from GitHub
3. Add the environment variables from `.env` in Railway's Variables tab
4. Railway will build and run the Dockerfile automatically

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Show help and your chat ID |
| `/check` | Manually trigger a badge check right now |

## Daily digest

The bot sends a message every day at `DAILY_HOUR:DAILY_MINUTE` UTC containing:

- 🎉 **Newly earned badges** since the last check
- 🎯 **Active challenges** you can still earn, with descriptions and end dates

## Notes

- Garmin Connect has no official public API — this uses the unofficial `garminconnect` library
- The bot stores state in `garmin_state.json` to track which badges it has already seen
- If Garmin enables 2FA on your account, you may need to generate a one-time token on first run
