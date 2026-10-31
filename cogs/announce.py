"""Slash commands for announcements and scheduled announcements.

All commands here are discord app_commands slash commands, guild-synced
by bot.py. There are no prefix commands and no plain-chat triggers in
this bot.

  /announce        <channel> <message> [ping_role]   (staff-only)
  /schedule        <channel> <YYYY-MM-DD HH:MM WIB> <message> [ping_role] (staff-only)
  /schedule_list
  /schedule_cancel <id>                              (staff-only)

Staff gate: see staff.is_staff — Administrator, Manage Guild, or a
staff role name. Non-staff users get an ephemeral refusal, never a
silent failure.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import db
from staff import is_staff
from timeparse import format_wib, parse_time


def _staff_only(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)


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
                "❌ This command is staff-only.", ephemeral=True)
            return
        text = f"{ping_role.mention}\n{message}" if ping_role else message
        await channel.send(text)
        await interaction.response.send_message(
            f"✅ Announcement sent to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="schedule", description="Schedule a one-off announcement (staff-only).")
    @app_commands.describe(
        channel="Channel to announce in",
        time="When: YYYY-MM-DD HH:MM WIB (relative times like 2h also work)",
        message="Announcement text",
        ping_role="Optional role to ping with the announcement")
    async def schedule(self, interaction: discord.Interaction,
                       channel: discord.TextChannel, time: str, message: str,
                       ping_role: discord.Role | None = None) -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                "❌ This command is staff-only.", ephemeral=True)
            return
        try:
            due = parse_time(time)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        sid = db.add_schedule(interaction.user.id,
                              interaction.guild.id if interaction.guild else None,
                              channel.id, message, due,
                              ping_role.id if ping_role else None)
        await interaction.response.send_message(
            f"✅ Scheduled announcement #{sid} for {format_wib(due.isoformat())} "
            f"in {channel.mention}.", ephemeral=True)

    @app_commands.command(name="schedule_list", description="List pending scheduled announcements.")
    async def schedule_list(self, interaction: discord.Interaction) -> None:
        rows = db.list_pending_schedules(
            interaction.guild.id if interaction.guild else None)
        if not rows:
            await interaction.response.send_message(
                "No scheduled announcements pending.", ephemeral=True)
            return
        lines = []
        for r in rows:
            ping = f" (ping <@&{r['ping_role_id']}>) " if r["ping_role_id"] else " "
            lines.append(f"#{r['id']} — {format_wib(r['due_at'])} in <#{r['channel_id']}>{ping}: {r['message']}")
        await interaction.response.send_message(
            "📅 Pending scheduled announcements:\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="schedule_cancel", description="Cancel a pending scheduled announcement (staff-only).")
    @app_commands.describe(id="The schedule ID from /schedule_list")
    async def schedule_cancel(self, interaction: discord.Interaction, id: int) -> None:
        if not _staff_only(interaction):
            await interaction.response.send_message(
                "❌ This command is staff-only.", ephemeral=True)
            return
        if db.cancel_schedule(id):
            await interaction.response.send_message(
                f"✅ Scheduled announcement #{id} cancelled.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ No pending scheduled announcement #{id} found.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Announce(bot))
