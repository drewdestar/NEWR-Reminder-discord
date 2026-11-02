"""Slash commands for announcements and scheduled announcements.

All commands here are discord app_commands slash commands, guild-synced
by bot.py. There are no prefix commands and no plain-chat triggers in
this bot.

  /announce        <channel> <message> [ping_role]   (staff-only)
  /schedule        <channel> <time> <message> [ping_role] [repeat] (staff-only)
  /schedule_list
  /schedule_cancel <id>                              (staff-only)
  /schedule_event  <name> <time> [description] <channel> (staff-only)

Staff gate: see staff.is_staff — Administrator, Manage Guild, or a
staff role name. Non-staff users get an ephemeral refusal, never a
silent failure.

/schedule_event creates a real Discord guild scheduled event and a
scheduled-announcement row for the same time/channel (so the
dispatcher also posts about it when it starts, with the event link).
Its event id is stored in SQLite alongside the announcement row.
/schedule_cancel best-effort deletes the linked guild event too, when
one exists; cancelling only the announcement row is still a success
if the event is already gone or cannot be deleted.

Command confirmations and errors are premium embeds from ui.py (same
ephemeral flags, same gates and logic as before). The announcement
itself sent to the target channel stays plain text on purpose: a
ping_role mention inside an embed does not ping.
"""
from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

import db
import ui
from staff import is_staff
from timeparse import format_wib, parse_time

REPEAT_CHOICES = [
    app_commands.Choice(name="No repeat", value="none"),
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
]


def _staff_only(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)


def _schedule_field(r):
    """One embed field per schedule, keeping id, WIB time, channel,
    ping role, repeat, event id and message (25-field limit applies)."""
    lines = [f"Channel: <#{r['channel_id']}>"]
    if r["ping_role_id"]:
        lines.append(f"Ping: <@&{r['ping_role_id']}>")
    try:
        if r["repeat"] and r["repeat"] != "none":
            lines.append(f"Repeat: {r['repeat']}")
        if r["event_id"]:
            lines.append(f"Event: {r['event_id']}")
    except (KeyError, IndexError, TypeError):
        pass
    lines.append(f"Message: {r['message']}")
    return (f"#{r['id']} • {format_wib(r['due_at'])}", "\n".join(lines), False)


def _describe_schedule(r) -> str:
    ping = f" (ping <@&{r['ping_role_id']}>) " if r["ping_role_id"] else " "
    extra = ""
    try:
        if r["repeat"] and r["repeat"] != "none":
            extra += f" ({r['repeat']})"
        if r["event_id"]:
            extra += f" [event {r['event_id']}]"
    except (KeyError, IndexError, TypeError):
        pass
    return (f"#{r['id']} • {format_wib(r['due_at'])} in "
            f"<#{r['channel_id']}>{ping}:{extra} {r['message']}")


class Announce(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="announce", description="Send an announcement to a channel now (staff-only).")
    @app_commands.describe(
        channel="Channel to announce in",
        message="Announcement text",
        ping_role="Optional role to ping with the announcement")
    async def announce(self, interaction: discord.Interaction,
                       channel: discord.TextChannel, message: str,
                       ping_role: discord.Role | None = None) -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                embed=ui.err("❌ Staff only", "This command is staff-only."),
                ephemeral=True)
            return
        if ping_role is None:
            text = message
        elif interaction.guild is not None and ping_role.id == interaction.guild.id:
            # @everyone role: its name is literally "@everyone", so a role
            # mention renders as "@@everyone" in the client. A literal
            # "@everyone" still pings everyone and renders as a single @.
            text = f"@everyone\n{message}"
        else:
            text = f"{ping_role.mention}\n{message}"
        # Deliberately plain text: a role mention inside an embed does
        # not ping, so the announcement itself is never embedded.
        await channel.send(text)
        await interaction.response.send_message(
            embed=ui.ok("✅ Announcement sent",
                        f"Announcement sent to {channel.mention}."),
            ephemeral=True)

    @app_commands.command(name="schedule", description="Schedule a one-off announcement (staff-only).")
    @app_commands.describe(
        channel="Channel to announce in",
        time="When: YYYY-MM-DD HH:MM WIB (relative times like 2h also work)",
        message="Announcement text",
        ping_role="Optional role to ping with the announcement",
        repeat="Repeat after firing: none, daily, or weekly")
    @app_commands.choices(repeat=REPEAT_CHOICES)
    async def schedule(self, interaction: discord.Interaction,
                       channel: discord.TextChannel, time: str, message: str,
                       ping_role: discord.Role | None = None,
                       repeat: str = "none") -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                embed=ui.err("❌ Staff only", "This command is staff-only."),
                ephemeral=True)
            return
        if repeat not in ("none", "daily", "weekly"):
            repeat = "none"
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(
                embed=ui.err("❌ Invalid time", str(e)), ephemeral=True)
            return
        sid = db.add_schedule(interaction.user.id,
                              interaction.guild.id if interaction.guild else None,
                              channel.id, message, due,
                              ping_role.id if ping_role else None,
                              repeat=repeat)
        fields = [
            ("When", format_wib(due.isoformat()), False),
            ("Channel", channel.mention, False),
        ]
        if repeat != "none":
            fields.append(("Repeat", repeat, False))
        await interaction.response.send_message(
            embed=ui.ok(f"✅ Scheduled announcement #{sid} set", None,
                        fields=fields),
            ephemeral=True)

    @app_commands.command(name="schedule_list", description="List pending scheduled announcements.")
    async def schedule_list(self, interaction: discord.Interaction) -> None:
        rows = db.list_pending_schedules(
            interaction.guild.id if interaction.guild else None)
        if not rows:
            await interaction.response.send_message(
                embed=ui.info("📅 No scheduled announcements",
                              "No scheduled announcements pending."),
                ephemeral=True)
            return
        if len(rows) <= 25:
            await interaction.response.send_message(
                embed=ui.info("📅 Pending scheduled announcements", None,
                              fields=[_schedule_field(r) for r in rows]),
                ephemeral=True)
        else:
            # Discord allows at most 25 embed fields; fall back to a
            # description list with the same data for very long lists.
            lines = [_describe_schedule(r) for r in rows]
            await interaction.response.send_message(
                embed=ui.info("📅 Pending scheduled announcements",
                              "\n".join(lines)),
                ephemeral=True)

    @app_commands.command(name="schedule_cancel", description="Cancel a pending scheduled announcement (staff-only).")
    @app_commands.describe(id="The schedule ID from /schedule_list")
    async def schedule_cancel(self, interaction: discord.Interaction, id: int) -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                embed=ui.err("❌ Staff only", "This command is staff-only."),
                ephemeral=True)
            return
        row = db.get_schedule(id)
        if row is None or row["done"]:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Not found",
                    f"No pending scheduled announcement #{id} found."),
                ephemeral=True)
            return
        event_note = ""
        try:
            event_id = row["event_id"]
        except (KeyError, IndexError, TypeError):
            event_id = None
        if event_id and interaction.guild is not None:
            try:
                event = await interaction.guild.fetch_scheduled_event(event_id)
                await event.delete()
                event_note = " Linked Discord event deleted too."
            except Exception:
                event_note = (" Linked Discord event could not be deleted "
                              "(it may already be gone).")
        if db.cancel_schedule(id):
            await interaction.response.send_message(
                embed=ui.ok(
                    "✅ Scheduled announcement cancelled",
                    f"Scheduled announcement #{id} cancelled.{event_note}"),
                ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Not found",
                    f"No pending scheduled announcement #{id} found."),
                ephemeral=True)

    @app_commands.command(name="schedule_event", description="Create a Discord scheduled event + announcement (staff-only).")
    @app_commands.describe(
        name="Event name",
        time="Start time: YYYY-MM-DD HH:MM WIB, or tomorrow 20:00, etc.",
        description="Event description (optional)",
        channel="Channel to announce it in when it starts")
    async def schedule_event(self, interaction: discord.Interaction,
                             name: str, time: str,
                             description: str = "",
                             channel: discord.TextChannel | None = None) -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                embed=ui.err("❌ Staff only", "This command is staff-only."),
                ephemeral=True)
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Server only",
                    "This command only works inside a server."),
                ephemeral=True)
            return
        if channel is None:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Channel needed",
                    "Please pick a channel to announce the event in."),
                ephemeral=True)
            return
        if not name.strip():
            await interaction.response.send_message(
                embed=ui.err("❌ Empty event name",
                             "Event name cannot be empty."),
                ephemeral=True)
            return
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(
                embed=ui.err("❌ Invalid time", str(e)), ephemeral=True)
            return
        # Create the guild event first; only record in SQLite on success,
        # so a failed event creation leaves no orphan announcement row.
        try:
            if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                event = await interaction.guild.create_scheduled_event(
                    name=name.strip(), start_time=due,
                    end_time=due + timedelta(hours=1),
                    description=description or None,
                    entity_type=discord.EntityType.voice,
                    channel=channel,
                    privacy_level=discord.PrivacyLevel.guild_only)
            else:
                event = await interaction.guild.create_scheduled_event(
                    name=name.strip(), start_time=due,
                    end_time=due + timedelta(hours=1),
                    description=description or None,
                    entity_type=discord.EntityType.external,
                    location=f"#{channel.name}",
                    privacy_level=discord.PrivacyLevel.guild_only)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Missing permission",
                    "I do not have permission to create scheduled events in "
                    "this server."),
                ephemeral=True)
            return
        except Exception as e:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Event creation failed",
                    f"Could not create the scheduled event: {e}"),
                ephemeral=True)
            return
        announcement_text = description.strip() if description.strip() else name.strip()
        sid = db.add_schedule(interaction.user.id, interaction.guild.id,
                              channel.id, announcement_text, due,
                              event_id=event.id)
        await interaction.response.send_message(
            embed=ui.ok(
                "✅ Event created", None,
                fields=[
                    ("Event", name.strip(), False),
                    ("When", format_wib(due.isoformat()), False),
                    ("Event id", str(event.id), False),
                    ("Announcement",
                     f"Scheduled announcement #{sid} will post in "
                     f"{channel.mention} when it starts, with the event link.",
                     False),
                ]),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Announce(bot))
