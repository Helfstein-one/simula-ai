"""domain/state.py - CoALA Cognitive Memory Models & State Definitions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


class ProceduralMemory(TypedDict, total=False):
    """Static system prompt, behavioral guidelines, constraints, and instructions."""
    role: str
    guidelines: List[str]
    system_prompt: str
    output_contract: str


class WorkingMemory(TypedDict, total=False):
    """Dynamic context for the current iteration."""
    contract_yaml: str
    contract_dict: Dict[str, Any]
    generated_code: Optional[str]
    pytest_output: Optional[str]
    pytest_exit_code: Optional[int]
    last_error: Optional[str]


class EpisodicMemoryRecord(TypedDict, total=False):
    """Historical trace of prior iteration attempts and failure modes."""
    iteration: int
    generated_code: str
    pytest_output: str
    exit_code: int
    error_summary: str
    timestamp: str
    traceback: str
    stdout: str
    reflection: str


class SimulaState(TypedDict, total=False):
    """Root CoALA State Schema for LangGraph orchestration."""
    procedural_memory: ProceduralMemory | Dict[str, Any]
    working_memory: WorkingMemory | Dict[str, Any]
    episodic_memory: List[EpisodicMemoryRecord]
    iterations: int
    max_iterations: int
    status: Literal["INIT", "GENERATING", "EXECUTING", "SUCCESS", "FAILED_MAX_RETRIES", "ERROR"] | str
    error_message: Optional[str]
