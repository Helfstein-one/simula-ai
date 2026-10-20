"""application/ports/state_repository_port.py - State & Episodic Memory Persistence Port."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from domain.state import SimulaState


@runtime_checkable
class StateRepositoryPort(Protocol):
    """Port interface for persisting CoALA checkpoints, episodic traces, and execution history."""

    def save_checkpoint(
        self,
        session_id: str,
        iteration: int,
        state: SimulaState,
        status: str = "",
        message: str = "",
    ) -> None:
        """Saves or updates a simulation checkpoint."""
        ...

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves checkpoint timeline for a specific simulation session."""
        ...

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists metadata of stored simulation sessions."""
        ...

    def export_session_jsonl(self, session_id: str, output_path: str) -> str:
        """Exports full trace of a session to JSONL file format."""
        ...
