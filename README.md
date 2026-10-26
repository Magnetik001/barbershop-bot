# Barbershop Booking Bot for Telegram

A Telegram bot that takes appointments instead of a receptionist. Clients pick a service, a barber and a time in five taps, while the owner and barbers see the schedule right in Telegram.

Works for barbershops, beauty salons, nail studios, massage therapists and any business where clients book a specific specialist.

<!-- Add a GIF or a link to the demo video here:
![Demo](docs/demo.gif)
-->

## Features

**For clients**
- Booking in a few taps: service, barber, day, time, confirmation
- Only free slots are shown; past times are hidden
- "My bookings": upcoming visits with one-tap cancellation
- Reminder 2 hours before the visit

**For the owner and barbers** (`/admin` command)
- Daily schedule: who is booked, for which service, and what is still free
- The owner sees every barber; a barber sees only their own schedule
- Number of bookings and revenue for the day
- Cancel a booking, and the client is notified automatically
- Close time for breaks, separate hours or a whole day off
- Instant owner notifications about new bookings and cancellations

**Reliability**
- Double booking is impossible, even if two clients tap at the same moment (unique index in the database)
- Bookings are stored in SQLite and survive restarts
- Admin panel access is checked on every action

<!-- Screenshots:
| Booking | Admin panel | Closing time |
|---|---|---|
| ![](docs/booking.png) | ![](docs/admin.png) | ![](docs/block.png) |
-->

## Tech stack

- Python 3.11+
- [aiogram 3](https://docs.aiogram.dev/), an asynchronous framework for the Telegram Bot API
- SQLite, a built-in database that needs no separate server

## Getting started

1. Create a bot with [@BotFather](https://t.me/BotFather) and get its token.
2. Get your Telegram ID from [@userinfobot](https://t.me/userinfobot).
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill it in:
   ```
   BOT_TOKEN=token_from_BotFather
   ADMIN_ID=your_telegram_id
   MASTER_IDS=alex:123456789,dima:987654321   # optional
   ```
5. Run the bot:
   ```bash
   python bot.py
   ```

To fill the schedule with sample bookings for a demo, run `python seed_demo.py` (remove them with `python seed_demo.py --clear`).

## Customizing for your business

Services, prices, barbers and opening hours are set at the top of `bot.py`:

```python
SERVICES = {
    "cut": ("Men's haircut", 25),
    "beard": ("Beard trim", 15),
    ...
}
MASTERS = {"alex": "Alex", "dima": "Dmitry", "ivan": "Ivan"}
CURRENCY = "$"
WORK_START, WORK_END = 10, 20   # opening hours
DAYS_AHEAD = 7                  # how many days ahead clients can book
```

## Project structure

```
bot.py            bot: client booking, reminders, admin panel
seed_demo.py      sample data for demos
requirements.txt  dependencies
.env.example      settings template
```

## Want a bot like this for your business?

I can set it up for your services and staff, then deploy it to a server.
Contact me on Telegram: <!-- @your_username -->
