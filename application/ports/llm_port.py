"""application/ports/llm_port.py - Language Model Provider Port."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from domain.state import EpisodicMemoryRecord, ProceduralMemory, WorkingMemory


@runtime_checkable
class LLMProviderPort(Protocol):
    """Port interface for generating candidate Python mock data code via LLMs."""

    def generate_candidate(
        self,
        procedural_memory: ProceduralMemory | Dict[str, Any] | None = None,
        working_memory: WorkingMemory | Dict[str, Any] | None = None,
        episodic_memory: List[EpisodicMemoryRecord] | None = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Synthesizes candidate Faker generator and Pytest validation code."""
        ...
