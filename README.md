# NEWR Reminder

Reminders and scheduled announcements for NEWR LABS. Slash commands
only, times in WIB (Asia/Jakarta).

`/remind`, `/remind_dm`, `/remind_list`, `/remind_edit`,
`/remind_cancel`, `/announce`, `/schedule`, `/schedule_list`,
`/schedule_cancel`, `/schedule_event`. Times accept things like `10m`,
`2h`, `1h30m`, `2026-11-02 09:00`, or `tomorrow 20:00`. Reminders can
repeat daily or weekly until cancelled.

Delivered reminders carry Snooze 10m / 1h buttons, and reacting with
the alarm-clock emoji to a message sets a DM reminder for 8 hours
later, linking back to that message.

Targeting another user or role is staff-only; everyone else can only
set reminders for themselves.

Run it:

```bash
bash ~/workspace/bots/ops/run-newr-reminder.sh
```

Token goes in `.env` (`DISCORD_TOKEN`, `GUILD_ID` is NEWR LABS). The
script sets up the venv and logs to
`~/workspace/bots/logs/newr-reminder.log`. Data lives in `data.db`
(SQLite, local).
