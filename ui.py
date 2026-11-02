"""Premium embed design system for NEWR Reminder.

Palette (matches the shared NEWR design system):
  blurple 0x5865F2 - primary / info
  success 0x57F287 - confirmations
  error   0xED4245 - denials and failures
  warning 0xFEE75C - cautions
  gold    0xF5C518 - reserved for starboard / leaderboard / rep;
                     deliberately NOT used by this bot.

Every embed carries the footer "NEWR Reminder • NEWR LABS" and a
timestamp via discord.utils.utcnow(). Titles use a single leading
emoji and plain sentence case, never ALL-CAPS shouting.
"""
from __future__ import annotations

import discord

BLURPLE = 0x5865F2
SUCCESS = 0x57F287
ERROR = 0xED4245
WARNING = 0xFEE75C
GOLD = 0xF5C518  # defined for palette completeness; not used here

FOOTER = "NEWR Reminder • NEWR LABS"


def panel(title: str, description: str | None, colour: int) -> discord.Embed:
    """Base embed: title, description, colour, footer and timestamp."""
    embed = discord.Embed(title=title, description=description, colour=colour)
    embed.set_footer(text=FOOTER)
    embed.timestamp = discord.utils.utcnow()
    return embed


def make(title: str, description: str | None, colour: int,
         fields: list[tuple[str, str, bool]] | list[tuple[str, str]] | None = None,
         thumbnail: str | None = None) -> discord.Embed:
    """Embed with optional fields and thumbnail.

    Each field is (name, value) or (name, value, inline).
    """
    embed = panel(title, description, colour)
    for field in fields or []:
        name, value = field[0], field[1]
        inline = field[2] if len(field) > 2 else False
        embed.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def ok(title: str, description: str | None = None,
       fields: list | None = None) -> discord.Embed:
    """Success embed (green)."""
    return make(title, description, SUCCESS, fields=fields)


def err(title: str, description: str | None = None,
        fields: list | None = None) -> discord.Embed:
    """Error / denial embed (red)."""
    return make(title, description, ERROR, fields=fields)


def warn(title: str, description: str | None = None,
         fields: list | None = None) -> discord.Embed:
    """Warning embed (yellow)."""
    return make(title, description, WARNING, fields=fields)


def info(title: str, description: str | None = None,
         fields: list | None = None) -> discord.Embed:
    """Info embed (blurple)."""
    return make(title, description, BLURPLE, fields=fields)
