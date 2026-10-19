"""domain/events.py - Domain lifecycle and streaming events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict


@dataclass
class SimulaEvent:
    """Event yielded during each phase of the CoALA cognitive cycle."""
    step: str
    iteration: int
    state: Dict[str, Any]
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
