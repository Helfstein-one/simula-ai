"""adapters/outbound/openrouter_adapter.py - Adapter for OpenRouter & Hermes AI generation."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from application.ports.llm_port import LLMProviderPort
from core.code_parser import CodeParser
from core.llm_client import (
    DEFAULT_PRIMARY_MODEL,
    MockLLMClient,
    OpenRouterClient,
)
from domain.state import EpisodicMemoryRecord, ProceduralMemory, WorkingMemory


class OpenRouterAdapter(LLMProviderPort):
    """Adapter implementing LLMProviderPort via OpenRouterClient or MockLLMClient."""

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: bool = False,
        client: Any = None,
    ) -> None:
        if client is not None:
            self.client = client
        else:
            is_mock = mock_mode or (os.environ.get("SIMULA_MOCK_LLM", "").lower() in ("true", "1", "yes"))
            if is_mock:
                self.client = MockLLMClient()
            else:
                self.client = OpenRouterClient(
                    model=model or DEFAULT_PRIMARY_MODEL,
                    api_key=api_key,
                )

    def generate_candidate(
        self,
        procedural_memory: ProceduralMemory | Dict[str, Any] | None = None,
        working_memory: WorkingMemory | Dict[str, Any] | None = None,
        episodic_memory: List[EpisodicMemoryRecord] | None = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Invokes LLM client and strips markdown fences and thinking tokens."""
        raw_output = self.client.generate_candidate(
            procedural_memory=procedural_memory or {},
            working_memory=working_memory or {},
            episodic_memory=episodic_memory or [],
            iteration=iteration,
            **kwargs,
        )
        return CodeParser.extract_python_code(raw_output)
