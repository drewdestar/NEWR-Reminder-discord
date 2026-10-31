"""Background delivery loop for NEWR Reminder.

A tasks.loop every 60 seconds checks SQLite for due reminders and
scheduled announcements, sends each one, then marks it done so it is
never resent. A failed send (e.g. DMs closed, channel deleted) is
logged and still marked done, so one bad row cannot block the queue
or spam on every tick. This cog has no user-facing command.
"""
from __future__ import annotations

import discord
from discord.ext import commands, tasks

import db


class Dispatcher(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.dispatch_loop.start()

    async def cog_unload(self) -> None:
        self.dispatch_loop.cancel()

    @tasks.loop(seconds=60)
    async def dispatch_loop(self) -> None:
        await self.bot.wait_until_ready()
        for row in db.due_items("reminders"):
            try:
                if row["dm"]:
                    user = self.bot.get_user(row["user_id"])
                    if user is None:
                        user = await self.bot.fetch_user(row["user_id"])
                    await user.send(f"⏰ Reminder: {row['message']}")
                else:
                    channel = self.bot.get_channel(row["channel_id"])
                    if channel is None:
                        channel = await self.bot.fetch_channel(row["channel_id"])
                    await channel.send(
                        f"⏰ Reminder for <@{row['user_id']}>: {row['message']}")
            except Exception as e:
                print(f"[dispatch] reminder #{row['id']} send failed: {e}")
            finally:
                db.mark_done("reminders", row["id"])
        for row in db.due_items("scheduled_announcements"):
            try:
                channel = self.bot.get_channel(row["channel_id"])
                if channel is None:
                    channel = await self.bot.fetch_channel(row["channel_id"])
                text = row["message"]
                if row["ping_role_id"]:
                    text = f"<@&{row['ping_role_id']}>\n{text}"
                await channel.send(text)
            except Exception as e:
                print(f"[dispatch] scheduled announcement #{row['id']} send failed: {e}")
            finally:
                db.mark_done("scheduled_announcements", row["id"])

    @dispatch_loop.before_loop
    async def _before_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Dispatcher(bot))
