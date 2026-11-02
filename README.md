# NEWR Reminder

A Discord bot for NEWR LABS (guild ID `1465422166790242377`) that sends
reminders and scheduled announcements. Times are entered in WIB
(Asia/Jakarta, UTC+7) and stored in SQLite as UTC.

## Slash commands only

**Every command in this bot is a slash command** (`discord.app_commands`,
guild-synced to NEWR LABS on startup). There are no prefix commands
(no `!remind`, no `!anything`), no plain-chat triggers, and no feature
that requires typing a prefix. Open the `/` command picker in NEWR LABS
and every feature below is there. Two non-command extras exist and are
marked as such below: Snooze buttons on delivered reminders, and a
⏰-reaction listener — neither is a slash command.

| Command | Who | What |
|---|---|---|
| `/remind <time> <message> [channel] [target_user] [target_role] [repeat]` | Anyone (targets: staff-only) | Reminder sent to a channel (default: the channel used); a user target with no channel is DM'd, a role target is mentioned in the channel |
| `/remind_list` | Anyone | List your own pending reminders |
| `/remind_cancel <id>` | Owner, or staff for any | Cancel a pending reminder |
| `/remind_dm <time> <message>` | Anyone | Reminder delivered to you by DM |
| `/remind_edit <id> [message] [time]` | Owner, or staff for any | Edit a pending reminder's message and/or time |
| `/announce <channel> <message> [ping_role]` | Staff-only | Announcement sent to a channel right now |
| `/schedule <channel> <time> <message> [ping_role] [repeat]` | Staff-only | Scheduled announcement (one-off, daily, or weekly) |
| `/schedule_list` | Anyone | List pending scheduled announcements |
| `/schedule_cancel <id>` | Staff-only | Cancel a pending scheduled announcement (deletes its linked Discord event too, if any) |
| `/schedule_event <name> <time> [description] <channel>` | Staff-only | Create a Discord guild scheduled event and a scheduled announcement for it (event id stored in SQLite) |

Total: 10 slash commands (under the 100-command limit).

### Non-command extras

- **Snooze buttons (on delivered reminders):** every delivered reminder
  message carries **Snooze 10m** and **Snooze 1h** buttons. Clicking one
  creates a new reminder for the clicking user with the same text, due
  after that delay, delivered the same way as the original (DM stays a
  DM, channel reminders stay in that channel). The buttons are kept in
  memory with a 24-hour timeout and are not restart-persistent: after
  a bot restart, old Snooze buttons stop responding, but any reminder
  already created by a click survives in SQLite.
- **React ⏰ to remind (event, not a command):** reacting with ⏰ to a
  guild message creates a DM reminder for the reacting user, due in
  8 hours, linking back to the original message (with a short quote).
  Bot reactions, reactions to the bot's own messages, and duplicate
  pending reminders for the same message are ignored.

## Time format

- Relative: `10m`, `2h`, `1d`, `30s`, `1w`, combinations like `1h30m` or `1h 30m`
  (counted from the moment the command runs).
- Absolute: `YYYY-MM-DD HH:MM` — interpreted as WIB, e.g. `2026-11-02 09:00 WIB`.
  Adding `UTC` instead (`2026-11-02 02:00 UTC`) interprets it as UTC.
- Natural language (WIB): `today 18:30`, `tomorrow 20:00`,
  `friday 19:00`, `next friday 19:00`, `next monday 09:00`
  (weekday names in full or 3-letter form). A bare weekday means the
  next occurrence of that weekday, today included if its time is still
  in the future; `next <weekday>` never means today — it is the first
  occurrence strictly after today (1–7 days ahead).
- A time in the past, or an unrecognised format, gets a clear error
  reply with format examples — the command never crashes on bad input.

## Recurring reminders

`/remind` and `/schedule` accept `repeat`: `none` (default), `daily`,
or `weekly`. When a recurring item fires, the dispatcher reschedules
it to its next occurrence (same time of day, +1 day or +7 days)
instead of marking it done. Cancel it with `/remind_cancel` or
`/schedule_cancel` to stop it.

## Targeting reminders

Without a target, `/remind` works exactly as before (for yourself).
Non-staff users may only target themselves — giving a user or role
target is refused. Staff may target one other user or one role (not
both): a user target with no channel is delivered by DM to that user;
a user target with a channel, and any role target, is delivered in
that channel mentioning the target. The reminder still belongs to the
staff member who set it for listing/cancelling purposes.

## Staff gate

Staff = Administrator permission, OR Manage Guild permission, OR a staff
role (see `staff.py`: NEWR LABS staff role names, plus a keyword fallback
for founder / executive / admin / moderator / helper / security /
support / staff roles). The guild owner always counts as staff.
Staff-only commands refuse non-staff users with an ephemeral message.

## Persistence

SQLite file `data.db` in this directory (created on first start), tables:

- `reminders` — id, user_id, guild_id, channel_id (NULL for DM),
  message, due_at (UTC ISO), created_at, done flag, dm flag,
  target_user_id, target_role_id, repeat, source_message_id,
  source_channel_id
- `scheduled_announcements` — id, user_id, guild_id, channel_id,
  message, due_at (UTC ISO), created_at, done flag, ping_role_id,
  repeat, event_id

A background loop (`cogs/dispatcher.py`) checks every 60 seconds for
due items, sends each one, then marks it done (or reschedules it, if
recurring) so it is never resent.

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
   required; Members intent is used for the staff gate). For
   `/schedule_event` it also needs Manage Events permission in the
   server; for the ⏰-reaction feature it needs to read the reacted
   message's channel.
4. Run it:
   ```bash
   bash ~/workspace/bots/ops/run-newr-reminder.sh
   ```
   The script creates `~/workspace/bots/newr-reminder/.venv` if needed,
   installs `requirements.txt`, and runs `python -u bot.py`, logging to
   `~/workspace/bots/logs/newr-reminder.log`.
   On startup you should see `Logged in as ...` and
   `Synced 10 slash commands to guild 1465422166790242377`.

## Still needed (not done — no token was available)

- A real `DISCORD_TOKEN` in `.env`
- Creating the Discord application / inviting the bot to NEWR LABS
- First live run (the bot was never started during the build)
