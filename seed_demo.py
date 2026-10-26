"""Fills the database with realistic bookings for demo videos and screenshots.

    python seed_demo.py          - add demo bookings for today and tomorrow
    python seed_demo.py --clear  - remove all demo bookings

Demo clients get negative user_id values, so they are easy to tell apart
and remove, and no reminders are sent to them.
"""
import random
import sys
from datetime import datetime, timedelta

import bot

CLIENTS = ["James", "Michael", "Daniel", "Ethan", "Ryan", "Lucas",
           "Nathan", "Oliver", "Leo", "Adam", "Sam", "Victor"]


def clear() -> int:
    with bot.db() as conn:
        return conn.execute("DELETE FROM bookings WHERE user_id < 0").rowcount


def seed(fill: float = 0.5) -> int:
    random.seed(7)
    now = datetime.now()
    added = 0
    for offset in (0, 1):
        day = (now.date() + timedelta(days=offset)).isoformat()
        for master in bot.MASTERS:
            # leave some slots free so there is something to pick in the video
            for t in bot.free_slots(master, day, now):
                if random.random() > fill:
                    continue
                booking_id = bot.create_booking(
                    -random.randint(1, 10**6), random.choice(CLIENTS),
                    random.choice(list(bot.SERVICES)), master, f"{day} {t}")
                if booking_id:
                    bot.mark_reminded(booking_id)
                    added += 1
    return added


if __name__ == "__main__":
    bot.init_db()
    if "--clear" in sys.argv:
        print(f"Demo bookings removed: {clear()}")
    else:
        print(f"Demo bookings added: {seed()}")
