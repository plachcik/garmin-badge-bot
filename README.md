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
  ⏰ Tylko dziś!! Rusz dupę!!
```
