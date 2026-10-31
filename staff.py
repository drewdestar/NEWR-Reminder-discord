"""Staff gate for NEWR Reminder.

Staff = Administrator permission, OR Manage Guild permission, OR a
staff role. The role check mirrors the existing newr-support pattern
(staff/admin/moderator/support categories) but is self-contained here
so this bot does not depend on newr-support's roles.py:
  - exact staff role names used in NEWR LABS, plus
  - keyword fallback (founder / executive / admin / moderator / mod /
    team lead / helper / security / support / staff) for renamed roles.
The guild owner always counts as staff. Permission checks alone are
sufficient; the role-name check is an extra path, not a replacement.
"""
from __future__ import annotations

import discord

STAFF_ROLE_NAMES: frozenset[str] = frozenset({
    "FOUNDER",
    "👑 Founder",
    "NEWR",
    "🏛️ Executive",
    "⭐ Admin",
    "🛡️ Senior Mod",
    "⚔️ Moderator",
    "🎯 Team Lead",
    "🤝 Helper",
    "Security",
})

_STAFF_KEYWORDS = ("founder", "executive", "admin", "senior mod", "moderator",
                   "team lead", "helper", "security", "support", "staff")


def is_staff(member: discord.abc.User) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild is not None and member.guild.owner_id == member.id:
        return True
    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild:
        return True
    for role in member.roles:
        if role.name in STAFF_ROLE_NAMES:
            return True
        low = role.name.lower()
        if any(k in low for k in _STAFF_KEYWORDS):
            return True
    return False
