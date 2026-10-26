"""Telegram bot for barbershop appointments.

Client: service -> barber -> day -> time -> confirmation.
My bookings + cancellation. Reminder 2 hours before the visit.
The owner (ADMIN_ID) is notified about new bookings and cancellations.
Admin panel /admin: daily schedule. The owner sees all barbers,
a barber (MASTER_IDS) sees only their own schedule.
"""
import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "barbershop.db")

# --- Barbershop settings -----------------------------------------------------
SERVICES = {
    "cut": ("Men's haircut", 25),
    "beard": ("Beard trim", 15),
    "combo": ("Haircut + beard", 35),
    "kids": ("Kids' haircut", 20),
}
MASTERS = {
    "alex": "Alex",
    "dima": "Dmitry",
    "ivan": "Ivan",
}
CURRENCY = "$"
WORK_START, WORK_END = 10, 20   # opening hours, one-hour slots
DAYS_AHEAD = 7                  # how many days ahead clients can book
REMIND_BEFORE = timedelta(hours=2)


def parse_master_ids(raw: str) -> dict[int, str]:
    """'alex:123,dima:456' -> {123: 'alex', 456: 'dima'}"""
    result = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        key, _, tg_id = pair.partition(":")
        if key in MASTERS and tg_id.strip().isdigit():
            result[int(tg_id)] = key
    return result


MASTER_IDS = parse_master_ids(os.getenv("MASTER_IDS", ""))


def staff_masters(user_id: int) -> list[str]:
    """Which barbers a user may see: the owner sees everyone, a barber sees themself."""
    if user_id == ADMIN_ID:
        return list(MASTERS)
    if user_id in MASTER_IDS:
        return [MASTER_IDS[user_id]]
    return []


# --- Database ----------------------------------------------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                service TEXT NOT NULL,
                master TEXT NOT NULL,
                starts_at TEXT NOT NULL,          -- 'YYYY-MM-DD HH:MM'
                status TEXT NOT NULL DEFAULT 'active',
                reminded INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
        # a barber can't have two active bookings at the same time
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_slot
            ON bookings(master, starts_at) WHERE status = 'active'""")
        # time closed by a barber (break, day off)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                master TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                PRIMARY KEY (master, starts_at)
            )""")


def blocked_slots(master: str, day: str) -> set[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT starts_at FROM blocks WHERE master=? AND starts_at LIKE ?",
            (master, f"{day}%")).fetchall()
    return {r["starts_at"][11:] for r in rows}


def toggle_block(master: str, starts_at: str) -> str | None:
    """Closes a free slot or reopens a closed one.
    Returns 'closed' / 'opened', or None if the slot is already booked."""
    with db() as conn:
        if conn.execute("DELETE FROM blocks WHERE master=? AND starts_at=?",
                        (master, starts_at)).rowcount:
            return "opened"
        cur = conn.execute(
            "INSERT INTO blocks(master, starts_at) SELECT ?, ? WHERE NOT EXISTS ("
            "SELECT 1 FROM bookings WHERE master=? AND starts_at=? AND status='active')",
            (master, starts_at, master, starts_at))
        return "closed" if cur.rowcount else None


def block_day(master: str, day: str, now: datetime | None = None) -> int:
    """Closes all free future slots of the day. Returns how many were closed."""
    slots = free_slots(master, day, now)
    for t in slots:
        toggle_block(master, f"{day} {t}")
    return len(slots)


def unblock_day(master: str, day: str) -> int:
    with db() as conn:
        return conn.execute("DELETE FROM blocks WHERE master=? AND starts_at LIKE ?",
                            (master, f"{day}%")).rowcount


def busy_slots(master: str, day: str) -> set[str]:
    with db() as conn:
        rows = conn.execute(
            "SELECT starts_at FROM bookings WHERE master=? AND status='active' "
            "AND starts_at LIKE ?", (master, f"{day}%")).fetchall()
    return {r["starts_at"][11:] for r in rows}


def free_slots(master: str, day: str, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    taken = busy_slots(master, day) | blocked_slots(master, day)
    result = []
    for h in range(WORK_START, WORK_END):
        t = f"{h:02d}:00"
        if t in taken:
            continue
        if datetime.strptime(f"{day} {t}", "%Y-%m-%d %H:%M") <= now:
            continue
        result.append(t)
    return result


def create_booking(user_id: int, user_name: str, service: str,
                   master: str, starts_at: str) -> int | None:
    try:
        with db() as conn:
            # a single statement, so a barber can't close the slot between check and insert
            cur = conn.execute(
                "INSERT INTO bookings(user_id, user_name, service, master, starts_at) "
                "SELECT ?,?,?,?,? WHERE NOT EXISTS ("
                "SELECT 1 FROM blocks WHERE master=? AND starts_at=?)",
                (user_id, user_name, service, master, starts_at, master, starts_at))
            return cur.lastrowid if cur.rowcount else None  # slot is closed
    except sqlite3.IntegrityError:
        return None  # slot was just taken


def user_bookings(user_id: int) -> list[sqlite3.Row]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with db() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE user_id=? AND status='active' "
            "AND starts_at > ? ORDER BY starts_at", (user_id, now)).fetchall()


def day_bookings(day: str, masters: list[str]) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(masters))
    with db() as conn:
        return conn.execute(
            f"SELECT * FROM bookings WHERE status='active' AND starts_at LIKE ? "
            f"AND master IN ({marks}) ORDER BY starts_at, master",
            (f"{day}%", *masters)).fetchall()


def get_booking(booking_id: int) -> sqlite3.Row | None:
    with db() as conn:
        return conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()


def cancel_booking(booking_id: int, user_id: int | None) -> sqlite3.Row | None:
    """Cancellation by the client (user_id) or by staff (user_id=None)."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND status='active' "
            "AND (? IS NULL OR user_id=?)",
            (booking_id, user_id, user_id)).fetchone()
        if row:
            conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?",
                         (booking_id,))
    return row


def due_reminders(now: datetime | None = None) -> list[sqlite3.Row]:
    now = now or datetime.now()
    lo = now.strftime("%Y-%m-%d %H:%M")
    hi = (now + REMIND_BEFORE).strftime("%Y-%m-%d %H:%M")
    with db() as conn:
        return conn.execute(
            "SELECT * FROM bookings WHERE status='active' AND reminded=0 "
            "AND starts_at > ? AND starts_at <= ?", (lo, hi)).fetchall()


def mark_reminded(booking_id: int) -> None:
    with db() as conn:
        conn.execute("UPDATE bookings SET reminded=1 WHERE id=?", (booking_id,))


# --- Formatting --------------------------------------------------------------
def fmt_day(day: str) -> str:
    return datetime.strptime(day, "%Y-%m-%d").strftime("%a, %b %d")


def fmt_price(amount: int) -> str:
    return f"{CURRENCY}{amount:,}"


def fmt_booking(b: sqlite3.Row) -> str:
    name, price = SERVICES[b["service"]]
    day, time = b["starts_at"].split()
    return (f"✂️ {name} — {fmt_price(price)}\n"
            f"👤 Barber: {MASTERS[b['master']]}\n"
            f"📅 {fmt_day(day)} at {time}")


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
        for row in rows])


MAIN_MENU = kb([[("📝 Book now", "book")], [("📋 My bookings", "my")]])


# --- Handlers ----------------------------------------------------------------
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Hi! I'm the barbershop bot 💈\nI'll book you with a barber in a few taps.",
        reply_markup=MAIN_MENU)


@dp.callback_query(F.data == "menu")
async def menu(cb: CallbackQuery):
    await cb.message.edit_text("Main menu:", reply_markup=MAIN_MENU)


@dp.callback_query(F.data == "book")
async def choose_service(cb: CallbackQuery):
    rows = [[(f"{n} — {fmt_price(p)}", f"s:{k}")] for k, (n, p) in SERVICES.items()]
    rows.append([("⬅️ Back", "menu")])
    await cb.message.edit_text("Choose a service:", reply_markup=kb(rows))


@dp.callback_query(F.data.startswith("s:"))
async def choose_master(cb: CallbackQuery):
    _, svc = cb.data.split(":")
    rows = [[(name, f"m:{svc}:{k}")] for k, name in MASTERS.items()]
    rows.append([("⬅️ Back", "book")])
    await cb.message.edit_text("Choose a barber:", reply_markup=kb(rows))


@dp.callback_query(F.data.startswith("m:"))
async def choose_day(cb: CallbackQuery):
    _, svc, master = cb.data.split(":")
    today = datetime.now().date()
    buttons = []
    for i in range(DAYS_AHEAD):
        day = (today + timedelta(days=i)).isoformat()
        if free_slots(master, day):
            buttons.append((fmt_day(day), f"d:{svc}:{master}:{day}"))
    if not buttons:
        await cb.answer("This barber has no free time this week", show_alert=True)
        return
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([("⬅️ Back", f"s:{svc}")])
    await cb.message.edit_text(f"Barber: {MASTERS[master]}. Choose a day:",
                               reply_markup=kb(rows))


@dp.callback_query(F.data.startswith("d:"))
async def choose_time(cb: CallbackQuery):
    _, svc, master, day = cb.data.split(":")
    if not free_slots(master, day):
        await cb.answer("This day is fully booked", show_alert=True)
        return
    await show_times(cb.message, svc, master, day)


async def show_times(message: Message, svc: str, master: str, day: str) -> None:
    buttons = [(t, f"t:{svc}:{master}:{day}:{t.replace(':', '')}")
               for t in free_slots(master, day)]
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([("⬅️ Back", f"m:{svc}:{master}")])
    await message.edit_text(f"{fmt_day(day)}. Choose a time:", reply_markup=kb(rows))


@dp.callback_query(F.data.startswith("t:"))
async def confirm(cb: CallbackQuery):
    _, svc, master, day, hhmm = cb.data.split(":")
    name, price = SERVICES[svc]
    text = (f"Please confirm your booking:\n\n✂️ {name} — {fmt_price(price)}\n"
            f"👤 Barber: {MASTERS[master]}\n📅 {fmt_day(day)} at {hhmm[:2]}:{hhmm[2:]}")
    await cb.message.edit_text(text, reply_markup=kb([
        [("✅ Confirm", f"ok:{svc}:{master}:{day}:{hhmm}")],
        [("⬅️ Another time", f"d:{svc}:{master}:{day}")]]))


@dp.callback_query(F.data.startswith("ok:"))
async def save(cb: CallbackQuery, bot: Bot):
    _, svc, master, day, hhmm = cb.data.split(":")
    starts_at = f"{day} {hhmm[:2]}:{hhmm[2:]}"
    user = cb.from_user
    user_name = f"{user.full_name}" + (f" (@{user.username})" if user.username else "")
    booking_id = create_booking(user.id, user_name, svc, master, starts_at)
    if booking_id is None:
        await cb.answer("Sorry, this time was just taken. Please choose another.",
                        show_alert=True)
        await show_times(cb.message, svc, master, day)
        return
    b = get_booking(booking_id)
    hours = int(REMIND_BEFORE.total_seconds() // 3600)
    await cb.message.edit_text(
        f"Done, you're booked! 🎉\n\n{fmt_booking(b)}\n\n"
        f"I'll remind you {hours} h before your visit.",
        reply_markup=MAIN_MENU)
    await notify_admin(bot, f"🆕 New booking #{booking_id}\n{user_name}\n\n{fmt_booking(b)}")


@dp.callback_query(F.data == "my")
async def my_bookings(cb: CallbackQuery):
    items = user_bookings(cb.from_user.id)
    if not items:
        await cb.message.edit_text("You have no upcoming bookings.", reply_markup=MAIN_MENU)
        return
    text = "Your bookings:\n\n" + "\n\n".join(fmt_booking(b) for b in items)
    rows = [[(f"❌ Cancel {fmt_day(b['starts_at'][:10])} {b['starts_at'][11:]}",
              f"c:{b['id']}")] for b in items]
    rows.append([("⬅️ Back", "menu")])
    await cb.message.edit_text(text, reply_markup=kb(rows))


@dp.callback_query(F.data.startswith("c:"))
async def cancel(cb: CallbackQuery, bot: Bot):
    b = cancel_booking(int(cb.data[2:]), cb.from_user.id)
    if not b:
        await cb.answer("Booking not found", show_alert=True)
        return
    await cb.answer("Booking cancelled")
    await my_bookings(cb)
    await notify_admin(bot, f"❌ Booking #{b['id']} cancelled\n{b['user_name']}\n\n{fmt_booking(b)}")


# --- Barber admin panel ------------------------------------------------------
def schedule_text(day: str, masters: list[str], now: datetime | None = None) -> str:
    """Daily schedule. One barber: hourly grid; all barbers: list of bookings."""
    now = now or datetime.now()
    items = day_bookings(day, masters)
    title = MASTERS[masters[0]] if len(masters) == 1 else "all barbers"
    lines = [f"📅 {fmt_day(day)} — {title}", ""]
    if len(masters) == 1:
        by_time = {b["starts_at"][11:]: b for b in items}
        blocked = blocked_slots(masters[0], day)
        for h in range(WORK_START, WORK_END):
            t = f"{h:02d}:00"
            if t in by_time:
                b = by_time[t]
                lines.append(f"{t} ✂️ {SERVICES[b['service']][0]} — {b['user_name']}")
            elif t in blocked:
                lines.append(f"{t} 🔒 closed")
            elif datetime.strptime(f"{day} {t}", "%Y-%m-%d %H:%M") <= now:
                lines.append(f"{t} ·")
            else:
                lines.append(f"{t} free")
    elif items:
        for b in items:
            lines.append(f"{b['starts_at'][11:]} {MASTERS[b['master']]}: "
                         f"{SERVICES[b['service']][0]} — {b['user_name']}")
    else:
        lines.append("No bookings.")
    total = sum(SERVICES[b["service"]][1] for b in items)
    lines += ["", f"Bookings: {len(items)} · Revenue: {fmt_price(total)}"]
    return "\n".join(lines)


def schedule_kb(day: str, view: str, allowed: list[str],
                now: datetime | None = None) -> InlineKeyboardMarkup:
    """view is a barber key or 'all'."""
    now = now or datetime.now()
    d = datetime.strptime(day, "%Y-%m-%d").date()
    prev_day = (d - timedelta(days=1)).isoformat()
    next_day = (d + timedelta(days=1)).isoformat()
    today = now.date().isoformat()
    rows = [[("◀️", f"a:{view}:{prev_day}"), ("Today", f"a:{view}:{today}"),
             ("▶️", f"a:{view}:{next_day}")]]
    if len(allowed) > 1:
        rows.append([("All" + (" •" if view == "all" else ""), f"a:all:{day}")] +
                    [(MASTERS[m] + (" •" if view == m else ""), f"a:{m}:{day}")
                     for m in allowed])
    if view != "all" and day >= today:
        rows.append([("🔒 Close / open time", f"bl:{view}:{day}")])
    masters = allowed if view == "all" else [view]
    now_str = now.strftime("%Y-%m-%d %H:%M")
    for b in day_bookings(day, masters):
        if b["starts_at"] > now_str:
            label = f"❌ Cancel {b['starts_at'][11:]}"
            if view == "all":
                label += f" {MASTERS[b['master']]}"
            rows.append([(label, f"ac:{b['id']}:{view}")])
    return kb(rows)


async def safe_edit(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


def resolve_view(user_id: int, view: str) -> tuple[list[str], list[str]] | None:
    """Checks access. Returns (allowed barbers, barbers to show)."""
    allowed = staff_masters(user_id)
    if not allowed:
        return None
    if view == "all" and len(allowed) > 1:
        return allowed, allowed
    if view in allowed:
        return allowed, [view]
    return None


@dp.message(Command("admin"))
async def admin(message: Message):
    allowed = staff_masters(message.from_user.id)
    if not allowed:
        await message.answer("This command is for barbers and the owner only.")
        return
    view = "all" if len(allowed) > 1 else allowed[0]
    day = datetime.now().date().isoformat()
    await message.answer(schedule_text(day, allowed if view == "all" else [view]),
                         reply_markup=schedule_kb(day, view, allowed))


@dp.callback_query(F.data.startswith("a:"))
async def admin_day(cb: CallbackQuery):
    _, view, day = cb.data.split(":")
    access = resolve_view(cb.from_user.id, view)
    if not access:
        await cb.answer("Access denied", show_alert=True)
        return
    allowed, masters = access
    await safe_edit(cb.message, schedule_text(day, masters),
                    schedule_kb(day, view, allowed))
    await cb.answer()


@dp.callback_query(F.data.startswith("ac:"))
async def admin_cancel(cb: CallbackQuery, bot: Bot):
    _, booking_id, view = cb.data.split(":")
    b = get_booking(int(booking_id))
    access = resolve_view(cb.from_user.id, view)
    if not b or not access or b["master"] not in access[1]:
        await cb.answer("Access denied", show_alert=True)
        return
    await cb.message.edit_text(
        f"Cancel this booking?\n\n{fmt_booking(b)}\nClient: {b['user_name']}\n\n"
        "The client will be notified.",
        reply_markup=kb([[("Yes, cancel", f"acy:{b['id']}:{view}")],
                         [("⬅️ Back", f"a:{view}:{b['starts_at'][:10]}")]]))


@dp.callback_query(F.data.startswith("acy:"))
async def admin_cancel_yes(cb: CallbackQuery, bot: Bot):
    _, booking_id, view = cb.data.split(":")
    b = get_booking(int(booking_id))
    access = resolve_view(cb.from_user.id, view)
    if not b or not access or b["master"] not in access[1]:
        await cb.answer("Access denied", show_alert=True)
        return
    day = b["starts_at"][:10]
    if cancel_booking(b["id"], None):
        await cb.answer("Booking cancelled")
        try:
            await bot.send_message(
                b["user_id"], f"😔 Sorry, the barbershop had to cancel your booking:\n\n"
                f"{fmt_booking(b)}\n\nPlease choose another time 👇", reply_markup=MAIN_MENU)
        except Exception as e:
            logging.warning("Client not notified about cancellation #%s: %s", b["id"], e)
        if cb.from_user.id != ADMIN_ID:
            await notify_admin(bot, f"❌ Barber cancelled booking #{b['id']}\n"
                                    f"{b['user_name']}\n\n{fmt_booking(b)}")
    else:
        await cb.answer("Booking is already cancelled", show_alert=True)
    allowed, masters = access
    await cb.message.edit_text(schedule_text(day, masters),
                               reply_markup=schedule_kb(day, view, allowed))


def block_kb(master: str, day: str, now: datetime | None = None) -> InlineKeyboardMarkup:
    """Slot grid: tapping a free slot closes it, tapping a 🔒 slot reopens it."""
    now = now or datetime.now()
    booked = busy_slots(master, day)
    blocked = blocked_slots(master, day)
    buttons = []
    for h in range(WORK_START, WORK_END):
        t = f"{h:02d}:00"
        if t in booked or datetime.strptime(f"{day} {t}", "%Y-%m-%d %H:%M") <= now:
            continue
        label = f"🔒 {t}" if t in blocked else t
        buttons.append((label, f"bt:{master}:{day}:{t.replace(':', '')}"))
    rows = [buttons[i:i + 4] for i in range(0, len(buttons), 4)]
    rows.append([("🔒 Close whole day", f"bd:{master}:{day}:1"),
                 ("🔓 Open all", f"bd:{master}:{day}:0")])
    rows.append([("⬅️ Back to schedule", f"a:{master}:{day}")])
    return kb(rows)


def block_text(master: str, day: str) -> str:
    return (f"📅 {fmt_day(day)} — {MASTERS[master]}\n\n"
            "Tap a time to close it for booking (break, day off). "
            "🔒 means already closed, tap again to reopen.\n"
            "Booked times are not shown here: cancel those bookings first.")


@dp.callback_query(F.data.startswith("bl:"))
async def block_menu(cb: CallbackQuery):
    _, master, day = cb.data.split(":")
    if not resolve_view(cb.from_user.id, master):
        await cb.answer("Access denied", show_alert=True)
        return
    await safe_edit(cb.message, block_text(master, day), block_kb(master, day))
    await cb.answer()


@dp.callback_query(F.data.startswith("bt:"))
async def block_toggle(cb: CallbackQuery):
    _, master, day, hhmm = cb.data.split(":")
    if not resolve_view(cb.from_user.id, master):
        await cb.answer("Access denied", show_alert=True)
        return
    result = toggle_block(master, f"{day} {hhmm[:2]}:{hhmm[2:]}")
    await cb.answer({"closed": "Time closed", "opened": "Time reopened"}.get(
        result, "This time has already been booked"))
    await safe_edit(cb.message, block_text(master, day), block_kb(master, day))


@dp.callback_query(F.data.startswith("bd:"))
async def block_whole_day(cb: CallbackQuery):
    _, master, day, close = cb.data.split(":")
    if not resolve_view(cb.from_user.id, master):
        await cb.answer("Access denied", show_alert=True)
        return
    if close == "1":
        n = block_day(master, day)
        await cb.answer(f"Slots closed: {n}")
    else:
        n = unblock_day(master, day)
        await cb.answer(f"Slots reopened: {n}")
    await safe_edit(cb.message, block_text(master, day), block_kb(master, day))


async def notify_admin(bot: Bot, text: str) -> None:
    if not ADMIN_ID:
        return
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:  # the owner may not have pressed /start yet
        logging.warning("Could not notify the owner: %s", e)


async def reminder_loop(bot: Bot) -> None:
    while True:
        for b in due_reminders():
            try:
                await bot.send_message(b["user_id"], f"⏰ Reminder about your booking:\n\n{fmt_booking(b)}")
            except Exception as e:
                logging.warning("Reminder #%s not delivered: %s", b["id"], e)
            mark_reminded(b["id"])
        await asyncio.sleep(60)


async def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN in the .env file (see .env.example)")
    logging.basicConfig(level=logging.INFO)
    init_db()
    bot = Bot(BOT_TOKEN)
    asyncio.create_task(reminder_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
