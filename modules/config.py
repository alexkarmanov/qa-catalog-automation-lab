"""Small typed settings object (successor of the empty 2023 ``config/config.py``). No secrets live here."""
from __future__ import annotations

from dataclasses import dataclass

CONNECT_TIMEOUT_S = 2.0
READ_TIMEOUT_S = 5.0
UI_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class Settings:
    connect_timeout: float = CONNECT_TIMEOUT_S
    read_timeout: float = READ_TIMEOUT_S
    ui_timeout_ms: int = UI_TIMEOUT_MS


DEFAULT = Settings()
