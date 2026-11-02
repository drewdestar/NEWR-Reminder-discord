"""Background delivery loop for NEWR Reminder.

A tasks.loop every 60 seconds checks SQLite for due reminders and
scheduled announcements. A one-off item is sent once, then marked
done so it is never resent. A recurring item (repeat daily/weekly)
is rescheduled to its next occurrence instead of being marked done.
A failed send (e.g. DMs closed, channel deleted) is logged; a one-off
item is still marked done so one bad row cannot block the queue or
spam on every tick, while a recurring item still advances to its
next occurrence.

Reminder messages carry Snooze buttons (10 minutes / 1 hour). Clicking
one creates a new reminder for the clicking user with the same text,
due after the chosen delay, delivered the same way as the original
(DM stays a DM, channel reminders stay in that channel). The view is
kept in memory with a 24-hour timeout; it is not restart-persistent,
so after a bot restart old Snooze buttons stop responding, but any
reminder already created by a click survives in SQLite.

Delivered reminders are premium embeds from ui.py, with the SnoozeView
attached exactly as before. For channel deliveries the target mention
is kept as the message content (not only inside the embed), because a
mention inside an embed does not ping; the embed carries the reminder
text and the same target info as a field. Scheduled announcements stay
plain text on purpose: they may contain a role ping and an event link,
both of which must work as plain text.

This cog also owns the ⏰-reaction feature (not a slash command):
reacting with ⏰ to a message creates a DM reminder for the reacting
user, due in 8 hours, linking back to the original message. Bot
reactions, reactions to the bot's own messages, and duplicate pending
reaction reminders for the same message are ignored.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

import db
import ui
from timeparse import next_recurrence

SNOOZE_TIMEOUT = 24 * 60 * 60  # seconds; view lives in memory only
REACTION_DELAY = timedelta(hours=8)
REACTION_EMOJI = "⏰"


class SnoozeView(discord.ui.View):
    """Snooze buttons attached to a delivered reminder.

    view.message_text / channel_id / dm / guild_id describe the
    original delivery, so a snoozed copy goes to the same place.
    """

    def __init__(self, message_text: str, channel_id: int | None,
                 dm: bool, guild_id: int | None) -> None:
        super().__init__(timeout=SNOOZE_TIMEOUT)
        self.message_text = message_text
        self.channel_id = channel_id
        self.dm = dm
        self.guild_id = guild_id

    async def _snooze(self, interaction: discord.Interaction,
                      delay: timedelta, label: str) -> None:
        try:
            due = datetime.now(timezone.utc) + delay
            rid = db.add_reminder(
                interaction.user.id, self.guild_id, self.channel_id,
                self.message_text, due, dm=self.dm)
            await interaction.response.send_message(
                embed=ui.ok(
                    "✅ Snoozed",
                    f"Snoozed for {label}. New reminder #{rid} for "
                    f"{due.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC."),
                ephemeral=True)
        except Exception as e:
            print(f"[snooze] failed: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=ui.err(
                            "❌ Snooze failed",
                            "Could not snooze this reminder. Please set a new "
                            "one with /remind."),
                        ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="Snooze 10m", style=discord.ButtonStyle.primary)
    async def snooze_10m(self, interaction: discord.Interaction,
                         button: discord.ui.Button) -> None:
        await self._snooze(interaction, timedelta(minutes=10), "10 minutes")

    @discord.ui.button(label="Snooze 1h", style=discord.ButtonStyle.secondary)
    async def snooze_1h(self, interaction: discord.Interaction,
                        button: discord.ui.Button) -> None:
        await self._snooze(interaction, timedelta(hours=1), "1 hour")


class Dispatcher(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.dispatch_loop.start()

    async def cog_unload(self) -> None:
        self.dispatch_loop.cancel()

    def _finish(self, table: str, row) -> None:
        """Mark done, or reschedule a recurring row to its next due."""
        repeat = ""
        try:
            repeat = row["repeat"] or "none"
        except (KeyError, IndexError, TypeError):
            repeat = "none"
        if repeat in ("daily", "weekly"):
            try:
                due = datetime.fromisoformat(
                    row["due_at"].replace("Z", "+00:00"))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                nxt = next_recurrence(due, repeat)
            except Exception:
                nxt = None
            if nxt is not None:
                db.update_due(table, row["id"], nxt)
                return
        db.mark_done(table, row["id"])

    @tasks.loop(seconds=60)
    async def dispatch_loop(self) -> None:
        await self.bot.wait_until_ready()
        for row in db.due_items("reminders"):
            try:
                view = SnoozeView(row["message"], row["channel_id"],
                                  bool(row["dm"]),
                                  row["guild_id"])
                if row["dm"]:
                    # DM delivery: to the target user if one was set,
                    # otherwise to the reminder owner.
                    target_id = row["target_user_id"] or row["user_id"]
                    user = self.bot.get_user(target_id)
                    if user is None:
                        user = await self.bot.fetch_user(target_id)
                    await user.send(
                        embed=ui.info("⏰ Reminder", row["message"]),
                        view=view)
                else:
                    channel = self.bot.get_channel(row["channel_id"])
                    if channel is None:
                        channel = await self.bot.fetch_channel(row["channel_id"])
                    if row["target_role_id"]:
                        target_mention = ("@everyone" if row["target_role_id"] == row["guild_id"] else f"<@&{row['target_role_id']}>")
                    elif row["target_user_id"]:
                        target_mention = f"<@{row['target_user_id']}>"
                    else:
                        target_mention = f"<@{row['user_id']}>"
                    # Mention stays as message content so it still
                    # pings; the embed carries the text and target info.
                    await channel.send(
                        content=target_mention,
                        embed=ui.info(
                            "⏰ Reminder", row["message"],
                            fields=[("For", target_mention, False)]),
                        view=view)
            except Exception as e:
                print(f"[dispatch] reminder #{row['id']} send failed: {e}")
            finally:
                self._finish("reminders", row)
        for row in db.due_items("scheduled_announcements"):
            try:
                channel = self.bot.get_channel(row["channel_id"])
                if channel is None:
                    channel = await self.bot.fetch_channel(row["channel_id"])
                text = row["message"]
                if row["ping_role_id"]:
                    ping = ("@everyone" if row["ping_role_id"] == row["guild_id"] else f"<@&{row['ping_role_id']}>")
                    text = f"{ping}\n{text}"
                try:
                    event_id = row["event_id"]
                except (KeyError, IndexError, TypeError):
                    event_id = None
                if event_id and row["guild_id"]:
                    text += (f"\nhttps://discord.com/events/"
                             f"{row['guild_id']}/{event_id}")
                # Deliberately plain text: a role ping and an event
                # link inside an embed would not ping / render as
                # plain clickable text the same way.
                await channel.send(text)
            except Exception as e:
                print(f"[dispatch] scheduled announcement #{row['id']} send failed: {e}")
            finally:
                self._finish("scheduled_announcements", row)

    @dispatch_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """⏰ reaction -> DM reminder in 8 hours about that message."""
        try:
            if str(payload.emoji) != REACTION_EMOJI:
                return
            if self.bot.user is not None and payload.user_id == self.bot.user.id:
                return
            member = getattr(payload, "member", None)
            if member is not None and getattr(member, "bot", False):
                return
            if payload.guild_id is None:
                return  # guild messages only; DM reactions have no jump link context
            channel = self.bot.get_channel(payload.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(payload.channel_id)
                except Exception:
                    return
            try:
                message = await channel.fetch_message(payload.message_id)
            except Exception:
                return
            if message.author.bot:
                return
            if self.bot.user is not None and message.author.id == self.bot.user.id:
                return
            if db.find_pending_reminder_by_source(payload.user_id,
                                                  payload.message_id):
                return  # already have a pending reminder for this message
            snippet = (message.content or "").strip().replace("\n", " ")
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            text = f"Message from <@{message.author.id}>: {message.jump_url}"
            if snippet:
                text += f"\n> {snippet}"
            db.add_reminder(payload.user_id, payload.guild_id, None, text,
                            datetime.now(timezone.utc) + REACTION_DELAY,
                            dm=True, source_message_id=payload.message_id,
                            source_channel_id=payload.channel_id)
        except Exception as e:
            print(f"[reaction-remind] failed: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Dispatcher(bot))
