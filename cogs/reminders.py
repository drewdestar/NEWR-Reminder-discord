"""Slash commands for personal reminders.

All commands here are discord app_commands slash commands, guild-synced
by bot.py. There are no prefix commands and no plain-chat triggers in
this bot: every feature is reached through the slash-command picker.

  /remind       <time> <message> [channel]
  /remind_list
  /remind_cancel <id>
  /remind_dm    <time> <message>

Times are parsed by timeparse.parse_time (relative like 10m/2h/1d/1h30m
or absolute YYYY-MM-DD HH:MM WIB) and stored as UTC in SQLite.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import db
from staff import is_staff
from timeparse import FORMAT_HELP, format_wib, parse_time


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="remind", description="Set a reminder in a channel (default: this channel).")
    @app_commands.describe(
        time="When: 10m, 2h, 1d, 1h30m, or YYYY-MM-DD HH:MM WIB",
        message="What to remind you about",
        channel="Channel to send it to (default: this channel)")
    async def remind(self, interaction: discord.Interaction, time: str,
                     message: str,
                     channel: discord.TextChannel | None = None) -> None:
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Please pick a text channel for this reminder, or use /remind_dm.",
                ephemeral=True)
            return
        rid = db.add_reminder(interaction.user.id,
                              interaction.guild.id if interaction.guild else None,
                              target.id, message, due, dm=False)
        await interaction.response.send_message(
            f"✅ Reminder #{rid} set for {format_wib(due.isoformat())} in {target.mention}.\n"
            f"Message: {message}", ephemeral=True)

    @app_commands.command(name="remind_list", description="List your pending reminders.")
    async def remind_list(self, interaction: discord.Interaction) -> None:
        rows = db.list_pending_reminders(
            interaction.user.id,
            interaction.guild.id if interaction.guild else None)
        if not rows:
            await interaction.response.send_message(
                "You have no pending reminders.", ephemeral=True)
            return
        lines = []
        for r in rows:
            dest = "DM" if r["dm"] else f"<#{r['channel_id']}>"
            lines.append(f"#{r['id']} — {format_wib(r['due_at'])} in {dest}: {r['message']}")
        await interaction.response.send_message(
            "⏰ Your pending reminders:\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="remind_cancel", description="Cancel one of your pending reminders.")
    @app_commands.describe(id="The reminder ID from /remind_list")
    async def remind_cancel(self, interaction: discord.Interaction, id: int) -> None:
        staff = is_staff(interaction.user) if isinstance(interaction.user, discord.Member) else False
        if db.cancel_reminder(id, interaction.user.id, staff=staff):
            await interaction.response.send_message(
                f"✅ Reminder #{id} cancelled.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ No pending reminder #{id} found for you.", ephemeral=True)

    @app_commands.command(name="remind_dm", description="Set a reminder delivered to you by DM.")
    @app_commands.describe(
        time="When: 10m, 2h, 1d, 1h30m, or YYYY-MM-DD HH:MM WIB",
        message="What to remind you about")
    async def remind_dm(self, interaction: discord.Interaction, time: str,
                        message: str) -> None:
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        rid = db.add_reminder(interaction.user.id,
                              interaction.guild.id if interaction.guild else None,
                              None, message, due, dm=True)
        await interaction.response.send_message(
            f"✅ DM reminder #{rid} set for {format_wib(due.isoformat())}.\n"
            f"Message: {message}\n"
            f"Note: I can only DM you if your DMs are open to server members.",
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
