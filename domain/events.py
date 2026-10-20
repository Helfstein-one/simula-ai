"""domain/events.py - Domain lifecycle and streaming events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Optional


@dataclass
class SimulaEvent:
    """Event yielded during each phase of the CoALA cognitive cycle."""
    step: str
    iteration: int
    state: Dict[str, Any]
    message: str = ""
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
