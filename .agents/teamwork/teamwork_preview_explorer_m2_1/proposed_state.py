"""core/state.py - Simula-AI CoALA Cognitive Loop State & Memory Definitions.

Defines the core data structures for the CoALA (Cognitive Architectures for
Language Agents) framework:
- Working Memory (short-term task artifacts and sandbox execution outputs)
- Episodic Memory (chronological execution history and failure traces)
- Procedural Memory (data engineering rules, Faker idioms, and test guidelines)
- SimulaState (top-level TypedDict tracking loop lifecycle and iteration bounds)
- SimulaEvent (streaming event dataclass for CLI spinners and Streamlit UI)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict


class EpisodicMemoryRecord(TypedDict):
    """Snapshot of a single execution attempt within the CoALA cognitive loop.

    Captures the candidate code, sandbox execution results, exit code,
    stdout/stderr streams, parsed test failure names, and condensed failure summary
    to enable reflection and self-correction in subsequent iterations.
    """

    iteration: int
    generated_code: str
    exit_code: int
    stdout: str
    stderr: str
    error_summary: str
    failed_tests: List[str]
    timestamp: str


class WorkingMemory(TypedDict, total=False):
    """Short-term workspace holding current cycle artifacts."""

    contract_yaml: str
    contract_dict: Optional[Dict[str, Any]]
    generated_code: Optional[str]
    pytest_output: Optional[str]
    pytest_exit_code: Optional[int]
    last_error: Optional[str]


class ProceduralMemory(TypedDict, total=False):
    """Static knowledge base of rules, idioms, and system instructions."""

    system_prompt: str
    faker_rules: List[str]
    relational_rules: List[str]
    pytest_rules: List[str]
    guidelines: List[str]
    rules: List[str]


StatusType = Literal[
    "INIT",
    "GENERATING",
    "EXECUTING",
    "RETRY",
    "SUCCESS",
    "FAILED_MAX_RETRIES",
    "FAILED",
    "ERROR",
]


class SimulaState(TypedDict, total=False):
    """Top-level agent state container passed across LangGraph nodes."""

    procedural_memory: ProceduralMemory
    working_memory: WorkingMemory
    episodic_memory: List[EpisodicMemoryRecord]
    iterations: int
    max_iterations: int
    status: StatusType
    error_message: Optional[str]
    model_name: Optional[str]
    run_id: Optional[str]


@dataclass
class SimulaEvent:
    """Event yielded during cognitive loop execution for real-time UI/CLI feedback."""

    step: str
    iteration: int
    state: SimulaState
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to serializable dictionary."""
        return {
            "step": self.step,
            "iteration": self.iteration,
            "message": self.message,
            "timestamp": self.timestamp,
            "status": self.state.get("status"),
            "pytest_exit_code": self.state.get("working_memory", {}).get("pytest_exit_code"),
        }


def create_initial_state(
    contract_yaml: str,
    max_iterations: int = 5,
    model_name: str = "deepseek/deepseek-r1",
    run_id: Optional[str] = None,
) -> SimulaState:
    """Constructs a clean initial SimulaState instance."""
    try:
        from core.memory import create_initial_procedural_memory
    except ImportError:
        from proposed_memory import create_initial_procedural_memory

    return {
        "procedural_memory": create_initial_procedural_memory(),
        "working_memory": {
            "contract_yaml": contract_yaml,
            "contract_dict": None,
            "generated_code": None,
            "pytest_output": None,
            "pytest_exit_code": None,
            "last_error": None,
        },
        "episodic_memory": [],
        "iterations": 0,
        "max_iterations": max_iterations,
        "status": "INIT",
        "error_message": None,
        "model_name": model_name,
        "run_id": run_id,
    }
