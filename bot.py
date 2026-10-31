"""NEWR Reminder bot entrypoint. Config comes only from environment variables.

Required: DISCORD_TOKEN, GUILD_ID (guild commands sync target).
Optional: DB_PATH.
Run:  bash ../ops/run-newr-reminder.sh   (or: pip install -r requirements.txt && python3 bot.py)

Slash commands ONLY: command_prefix=None, help_command=None, and no
on_message handler anywhere in this bot. Every feature is a discord
app_commands slash command, guild-synced to NEWR LABS on ready.
There are no prefix commands (!remind etc.) and no plain-chat triggers.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv  # optional, only if installed
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402

COGS = ["cogs.reminders", "cogs.announce", "cogs.dispatcher"]
# Guild-sync target: NEWR LABS. The placeholder .env holds only
# DISCORD_TOKEN, so default to this guild when GUILD_ID is unset;
# an explicit GUILD_ID in .env overrides it. Never sync globally.
NEWR_LABS_GUILD_ID = 1465422166790242377
try:
    GUILD_ID = int(os.environ["GUILD_ID"]) if os.environ.get("GUILD_ID") else NEWR_LABS_GUILD_ID
except ValueError:
    GUILD_ID = NEWR_LABS_GUILD_ID


def _proxy_kwargs() -> dict:
    """Copied from newr-support/bot.py: VM egress goes through an HTTP
    proxy; direct TLS to Discord fails here, while aiohttp with
    trust_env works. discord.py does not read proxy env vars itself,
    so pass them explicitly. Credentials stay in the environment,
    never in code or logs."""
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    if not raw:
        return {}
    parsed = urlparse(raw)
    proxy = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 3128}"
    kwargs: dict = {"proxy": proxy}
    if parsed.username:
        import aiohttp

        kwargs["proxy_auth"] = aiohttp.BasicAuth(
            unquote(parsed.username),
            unquote(parsed.password or ""))
    return kwargs


class ReminderBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True  # needed for the staff role/permission gate
        intents.messages = True
        intents.dm_messages = True  # needed for /remind_dm delivery
        # Slash commands only: no prefix, no help command, no on_message.
        super().__init__(command_prefix=None, intents=intents, help_command=None,
                         **_proxy_kwargs())
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        db.init_db()
        for cog in COGS:
            await self.load_extension(cog)

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (id={self.user.id})")
        if getattr(self, "_synced", False):
            return
        self._synced = True
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash commands to guild {GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash commands globally")


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. See .env.example.")
    import asyncio
    asyncio.run(ReminderBot().start(token))


if __name__ == "__main__":
    main()
