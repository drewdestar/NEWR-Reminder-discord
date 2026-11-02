"""Slash commands for personal reminders.

All commands here are discord app_commands slash commands, guild-synced
by bot.py. There are no prefix commands and no plain-chat triggers in
this bot: every feature is reached through the slash-command picker
(the ⏰-reaction feature lives in cogs/dispatcher.py and is an event,
not a command).

  /remind       <time> <message> [channel] [target_user] [target_role] [repeat]
  /remind_list
  /remind_cancel <id>
  /remind_dm    <time> <message>
  /remind_edit  <id> [message] [time]

Times are parsed by timeparse.parse_time (relative like 10m/2h/1d/1h30m,
absolute YYYY-MM-DD HH:MM WIB, or natural like tomorrow 20:00 /
next friday 19:00) and stored as UTC in SQLite.

Targeting rule: without a target the reminder is for yourself, exactly
as before. Non-staff users may only target themselves (giving a
target_user or target_role is refused); staff may target another user
or a role. A user target with no channel given is delivered by DM to
that user; a user target with a channel given, and any role target,
is delivered in that channel mentioning the target.

Replies are premium embeds from ui.py (same ephemeral flags, same
data, same gates and logic as before); only the presentation changed.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import db
import ui
from staff import is_staff
from timeparse import FORMAT_HELP, format_wib, parse_time

REPEAT_CHOICES = [
    app_commands.Choice(name="No repeat", value="none"),
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
]


def _is_staff(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)


def _describe_row(r) -> str:
    dest = "DM" if r["dm"] else f"<#{r['channel_id']}>"
    extra = ""
    try:
        if r["target_user_id"]:
            extra += f" for <@{r['target_user_id']}>"
        elif r["target_role_id"]:
            extra += f" for <@&{r['target_role_id']}>"
        if r["repeat"] and r["repeat"] != "none":
            extra += f" ({r['repeat']})"
    except (KeyError, IndexError, TypeError):
        pass
    return f"#{r['id']} • {format_wib(r['due_at'])} in {dest}{extra}: {r['message']}"


def _row_field(r):
    """One embed field per reminder, keeping id, WIB time, destination,
    target, repeat and message (used while the list fits in 25 fields)."""
    dest = "DM" if r["dm"] else f"<#{r['channel_id']}>"
    lines = [f"Destination: {dest}"]
    try:
        if r["target_user_id"]:
            lines.append(f"Target: <@{r['target_user_id']}>")
        elif r["target_role_id"]:
            lines.append(f"Target: <@&{r['target_role_id']}>")
        if r["repeat"] and r["repeat"] != "none":
            lines.append(f"Repeat: {r['repeat']}")
    except (KeyError, IndexError, TypeError):
        pass
    lines.append(f"Message: {r['message']}")
    return (f"#{r['id']} • {format_wib(r['due_at'])}", "\n".join(lines), False)


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="remind", description="Set a reminder in a channel (default: this channel).")
    @app_commands.describe(
        time="When: 10m, 2h, 1d, 1h30m, YYYY-MM-DD HH:MM WIB, or tomorrow 20:00",
        message="What to remind about",
        channel="Channel to send it to (default: this channel)",
        target_user="Staff-only: another user to remind (no channel = DM to them)",
        target_role="Staff-only: a role to remind in the channel",
        repeat="Repeat after firing: none, daily, or weekly")
    @app_commands.choices(repeat=REPEAT_CHOICES)
    async def remind(self, interaction: discord.Interaction, time: str,
                     message: str,
                     channel: discord.TextChannel | None = None,
                     target_user: discord.Member | None = None,
                     target_role: discord.Role | None = None,
                     repeat: str = "none") -> None:
        staff = _is_staff(interaction)
        if (target_user is not None or target_role is not None) and not staff:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Staff only",
                    "Only staff can set reminders for other users or roles. "
                    "Leave the target blank to remind yourself."),
                ephemeral=True)
            return
        if target_user is not None and target_role is not None:
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ One target only",
                    "Pick only one target: a user or a role, not both."),
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
        if target_user is not None and channel is None:
            # DM delivery to the target user.
            rid = db.add_reminder(
                interaction.user.id,
                interaction.guild.id if interaction.guild else None,
                None, message, due, dm=True,
                target_user_id=target_user.id, repeat=repeat)
            fields = [
                ("When", format_wib(due.isoformat()), False),
                ("Delivery", f"DM to {target_user.mention}", False),
                ("Message", message, False),
            ]
            if repeat != "none":
                fields.append(("Repeat", repeat, False))
            await interaction.response.send_message(
                embed=ui.ok(f"✅ Reminder #{rid} set", None, fields=fields),
                ephemeral=True)
            return
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Text channel needed",
                    "Please pick a text channel for this reminder, or use /remind_dm."),
                ephemeral=True)
            return
        rid = db.add_reminder(
            interaction.user.id,
            interaction.guild.id if interaction.guild else None,
            target.id, message, due, dm=False,
            target_user_id=target_user.id if target_user else None,
            target_role_id=target_role.id if target_role else None,
            repeat=repeat)
        if target_user is not None:
            dest_text = f"for {target_user.mention} in {target.mention}"
        elif target_role is not None:
            dest_text = f"for {target_role.mention} in {target.mention}"
        else:
            dest_text = f"in {target.mention}"
        fields = [
            ("When", format_wib(due.isoformat()), False),
            ("Delivery", dest_text, False),
            ("Message", message, False),
        ]
        if repeat != "none":
            fields.append(("Repeat", repeat, False))
        await interaction.response.send_message(
            embed=ui.ok(f"✅ Reminder #{rid} set", None, fields=fields),
            ephemeral=True)

    @app_commands.command(name="remind_list", description="List your pending reminders.")
    async def remind_list(self, interaction: discord.Interaction) -> None:
        rows = db.list_pending_reminders(
            interaction.user.id,
            interaction.guild.id if interaction.guild else None)
        if not rows:
            await interaction.response.send_message(
                embed=ui.info("⏰ No pending reminders",
                              "You have no pending reminders."),
                ephemeral=True)
            return
        if len(rows) <= 25:
            await interaction.response.send_message(
                embed=ui.info("⏰ Your pending reminders", None,
                              fields=[_row_field(r) for r in rows]),
                ephemeral=True)
        else:
            # Discord allows at most 25 embed fields; fall back to a
            # description list with the same data for very long lists.
            lines = [_describe_row(r) for r in rows]
            await interaction.response.send_message(
                embed=ui.info("⏰ Your pending reminders",
                              "\n".join(lines)),
                ephemeral=True)

    @app_commands.command(name="remind_cancel", description="Cancel one of your pending reminders.")
    @app_commands.describe(id="The reminder ID from /remind_list")
    async def remind_cancel(self, interaction: discord.Interaction, id: int) -> None:
        staff = _is_staff(interaction)
        if db.cancel_reminder(id, interaction.user.id, staff=staff):
            await interaction.response.send_message(
                embed=ui.ok("✅ Reminder cancelled",
                            f"Reminder #{id} cancelled."),
                ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=ui.err("❌ Not found",
                             f"No pending reminder #{id} found for you."),
                ephemeral=True)

    @app_commands.command(name="remind_dm", description="Set a reminder delivered to you by DM.")
    @app_commands.describe(
        time="When: 10m, 2h, 1d, 1h30m, YYYY-MM-DD HH:MM WIB, or tomorrow 20:00",
        message="What to remind you about")
    async def remind_dm(self, interaction: discord.Interaction, time: str,
                        message: str) -> None:
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(
                embed=ui.err("❌ Invalid time", str(e)), ephemeral=True)
            return
        rid = db.add_reminder(interaction.user.id,
                              interaction.guild.id if interaction.guild else None,
                              None, message, due, dm=True)
        await interaction.response.send_message(
            embed=ui.ok(
                f"✅ DM reminder #{rid} set",
                "Note: I can only DM you if your DMs are open to server members.",
                fields=[
                    ("When", format_wib(due.isoformat()), False),
                    ("Message", message, False),
                ]),
            ephemeral=True)

    @app_commands.command(name="remind_edit", description="Edit a pending reminder's message and/or time.")
    @app_commands.describe(
        id="The reminder ID from /remind_list",
        message="New message text (leave blank to keep the current one)",
        time="New time, same formats as /remind (leave blank to keep the current one)")
    async def remind_edit(self, interaction: discord.Interaction, id: int,
                          message: str | None = None,
                          time: str | None = None) -> None:
        if (message is None or message == "") and (time is None or time == ""):
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Nothing to change",
                    "Give a new message and/or a new time.\n"
                    f"Time formats: {FORMAT_HELP}"),
                ephemeral=True)
            return
        row = db.get_reminder(id)
        if row is None or row["done"]:
            await interaction.response.send_message(
                embed=ui.err("❌ Not found",
                             f"No pending reminder #{id} found."),
                ephemeral=True)
            return
        staff = _is_staff(interaction)
        if row["user_id"] != interaction.user.id and not staff:
            await interaction.response.send_message(
                embed=ui.err("❌ Not your reminder",
                             "You can only edit your own reminders."),
                ephemeral=True)
            return
        due = None
        if time:
            try:
                due = parse_time(time)
            except ValueError as e:
                await interaction.response.send_message(
                    embed=ui.err("❌ Invalid time", str(e)), ephemeral=True)
                return
        new_message = message if message else None
        if not db.update_reminder(id, message=new_message, due_at=due):
            await interaction.response.send_message(
                embed=ui.err(
                    "❌ Update failed",
                    f"Reminder #{id} could not be updated (it may have just fired)."),
                ephemeral=True)
            return
        updated = db.get_reminder(id)
        await interaction.response.send_message(
            embed=ui.ok(
                f"✅ Reminder #{id} updated", None,
                fields=[
                    ("When", format_wib(updated['due_at']), False),
                    ("Message", updated['message'], False),
                ]),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
