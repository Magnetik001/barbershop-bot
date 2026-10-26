# Demo video script (45-60 seconds)

The goal is to show a barbershop owner in one minute that clients book on their own and the owner sees everything on their phone. Show the result, not the code.

## Preparation (5 minutes)

1. **Fill the schedule** so it looks busy:
   ```bash
   python seed_demo.py
   ```
   Remove the demo data after recording: `python seed_demo.py --clear`.
2. **Two screens.** You play both the client and the owner from one account, which is fine. The easiest setup:
   - Telegram on your phone as the client (phone screen recording);
   - Telegram Desktop on your computer as the owner (recorded with OBS or Win+G).
   Or record everything on the phone, switching to the chat with the notifications.
3. **Clean up the chat** with the bot: delete old test messages so `/start` comes first.
4. Turn on Do Not Disturb so other notifications don't show up.
5. Dark or light theme, either is fine, but keep one for the whole video.

## Scenes

| # | Time | On screen | Caption |
|---|---|---|---|
| 1 | 0-3 s | Chat with the bot, tap `/start` | **Telegram booking bot for barbershops** |
| 2 | 3-15 s | Book now, "Haircut + beard", barber Alex, day, time, Confirm. Tap calmly, about 1 second per step | Clients book on their own: 5 taps, 24/7 |
| 3 | 15-20 s | The "Done, you're booked!" message | A reminder 2 hours before means fewer no-shows |
| 4 | 20-25 s | Owner notification "New booking" | The owner learns about every booking instantly |
| 5 | 25-35 s | `/admin`, schedule of all barbers, switch to Alex, hourly grid and revenue | Daily schedule and revenue on one screen |
| 6 | 35-45 s | "Close / open time", close 14:00, back to the schedule: 14:00 closed | A barber closes time for a break or a day off |
| 7 | 45-52 s | Client: "My bookings", Cancel, owner receives "Booking cancelled" | One-tap cancellation frees the slot |
| 8 | 52-60 s | Static final frame | **I'll build a bot like this for your business** · Telegram @Magnetik001 |

## Editing

- Cut pauses and waiting: no dead seconds in the video.
- Large captions at the bottom of the frame, since many people watch without sound.
- Quiet music without lyrics (free libraries in CapCut or the YouTube Audio Library).
- Format: vertical 9:16 if you record the phone (Kwork, Telegram, Reels); horizontal 16:9 if you record the computer.
- Tools: **CapCut** (free, on phone and PC) is enough for everything above.

## Where to post it

- Service cover and description on Kwork
- GitHub README (a GIF of the first 15 seconds as `docs/demo.gif`)
- Your Telegram channel or stories
- Direct messages to barbershop owners: the video plus a one-line offer
