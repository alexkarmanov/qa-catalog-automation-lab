"""Role/action matrix of the sandbox (contract section 1)."""
from __future__ import annotations

ROLES = ("viewer", "editor", "publisher")

READ_DRAFT_ROLES = frozenset({"editor", "publisher"})
CREATE_ROLES = frozenset({"editor", "publisher"})
EDIT_ROLES = frozenset({"editor", "publisher"})
PUBLISH_ROLES = frozenset({"publisher"})


def can_read_drafts(role: str) -> bool:
    return role in READ_DRAFT_ROLES
