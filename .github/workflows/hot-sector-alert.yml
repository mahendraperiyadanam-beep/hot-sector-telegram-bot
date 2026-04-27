# Hot Sector / Industry / Stock Leader Telegram Bot

This GitHub Actions bot sends a Telegram alert at:

- 5:00 AM Pacific
- 6:30 AM Pacific
- 9:00 AM Pacific
- 11:00 AM Pacific

It identifies:

1. Hot sectors using sector ETFs such as XLK, XLE, XLF, XLV, etc.
2. Hot industries/themes using ETFs such as SMH, IGV, XBI, KRE, XOP, ITB, etc.
3. Stock leaders inside the hot sectors using S&P 500 constituents.

## What the ranking looks for

The score favors:

- Strong 1-day, 5-day, 20-day, and 63-day return
- Relative strength versus SPY
- High relative volume
- High dollar volume
- Price above 20-day / 50-day / 200-day moving averages
- Stocks near 20-day highs

## GitHub setup

### 1. Create a new GitHub repository

Example name:

```text
hot-sector-telegram-bot
```

### 2. Upload these files

Upload the full folder contents into the repo.

### 3. Add GitHub secrets

Go to:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Add:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

### 4. Get Telegram bot token

In Telegram:

1. Open `@BotFather`
2. Run `/newbot`
3. Copy the bot token
4. Add it to GitHub as `TELEGRAM_BOT_TOKEN`

### 5. Get your Telegram chat id

Easy method:

1. Send any message to your bot.
2. In a browser, open:

```text
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

3. Find `"chat":{"id":...}`
4. Add that number as `TELEGRAM_CHAT_ID`

### 6. Test manually

In GitHub:

```text
Actions → Hot Sector Telegram Alerts → Run workflow
```

Leave `force_send = true`.

## Schedule logic

GitHub Actions cron is UTC. This repo schedules both PST and PDT UTC equivalents.  
The Python code checks `America/Los_Angeles` time before sending, so daylight saving time should not cause wrong-time Telegram alerts.

## Customization

Edit:

```text
src/config.py
```

Common changes:

- Add industry ETFs
- Change top sector count
- Change number of leaders
- Tighten filters using `MIN_PRICE` and `MIN_DOLLAR_VOLUME`

## Disclaimer

This is a market scanner, not financial advice. Always confirm with charts, risk management, and your own trading rules.
