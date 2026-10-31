# NEWR Reminder

A Discord bot for NEWR LABS (guild ID `1465422166790242377`) that sends
reminders and scheduled announcements. Times are entered in WIB
(Asia/Jakarta, UTC+7) and stored in SQLite as UTC.

## Slash commands only

**Every command in this bot is a slash command** (`discord.app_commands`,
guild-synced to NEWR LABS on startup). There are no prefix commands
(no `!remind`, no `!anything`), no plain-chat triggers, and no feature
that requires typing a prefix. Open the `/` command picker in NEWR LABS
and every feature below is there.

| Command | Who | What |
|---|---|---|
| `/remind <time> <message> [channel]` | Anyone | Reminder sent to a channel (default: the channel used) |
| `/remind_list` | Anyone | List your own pending reminders |
| `/remind_cancel <id>` | Owner, or staff for any | Cancel a pending reminder |
| `/remind_dm <time> <message>` | Anyone | Reminder delivered to you by DM |
| `/announce <channel> <message> [ping_role]` | Staff-only | Announcement sent to a channel right now |
| `/schedule <channel> <time> <message> [ping_role]` | Staff-only | One-off scheduled announcement |
| `/schedule_list` | Anyone | List pending scheduled announcements |
| `/schedule_cancel <id>` | Staff-only | Cancel a pending scheduled announcement |

Total: 8 slash commands (under the 30-command limit).

## Time format

- Relative: `10m`, `2h`, `1d`, `30s`, `1w`, combinations like `1h30m` or `1h 30m`
  (counted from the moment the command runs).
- Absolute: `YYYY-MM-DD HH:MM` — interpreted as WIB, e.g. `2026-11-02 09:00 WIB`.
  Adding `UTC` instead (`2026-11-02 02:00 UTC`) interprets it as UTC.
- A time in the past, or an unrecognised format, gets a clear error
  reply with format examples — the command never crashes on bad input.

## Staff gate

Staff = Administrator permission, OR Manage Guild permission, OR a staff
role (see `staff.py`: NEWR LABS staff role names, plus a keyword fallback
for founder / executive / admin / moderator / helper / security /
support / staff roles). The guild owner always counts as staff.
Staff-only commands refuse non-staff users with an ephemeral message.

## Persistence

SQLite file `data.db` in this directory (created on first start), tables:

- `reminders` — id, user_id, guild_id, channel_id (NULL for DM),
  message, due_at (UTC ISO), created_at, done flag, dm flag
- `scheduled_announcements` — id, user_id, guild_id, channel_id,
  message, due_at (UTC ISO), created_at, done flag, ping_role_id

A background loop (`cogs/dispatcher.py`) checks every 60 seconds for
due items, sends each one, then marks it done so it is never resent.

## Setup

1. Create a Discord application + bot (not done by the build — see
   "Still needed" below), copy its token.
2. Copy `.env.example` to `.env` and put the token in `DISCORD_TOKEN`
   (`.env` is chmod 600; never commit it, never paste the token in chat).
   `GUILD_ID` is already `1465422166790242377` in `.env.example`.
   If `GUILD_ID` is missing from `.env`, the bot defaults to that same
   guild ID rather than syncing globally.
3. Invite the bot to NEWR LABS with the `bot` + `applications.commands`
   scopes (it needs Send Messages, and Read Message History is not
   required; Members intent is used for the staff gate).
4. Run it:
   ```bash
   bash ~/workspace/bots/ops/run-newr-reminder.sh
   ```
   The script creates `~/workspace/bots/newr-reminder/.venv` if needed,
   installs `requirements.txt`, and runs `python -u bot.py`, logging to
   `~/workspace/bots/logs/newr-reminder.log`.
   On startup you should see `Logged in as ...` and
   `Synced 8 slash commands to guild 1465422166790242377`.

## Still needed (not done — no token was available)

- A real `DISCORD_TOKEN` in `.env`
- Creating the Discord application / inviting the bot to NEWR LABS
- First live run (the bot was never started during the build)
