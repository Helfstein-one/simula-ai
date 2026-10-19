"""application/ports/sandbox_port.py - Code Execution Sandbox Port & Result Value Object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable


@dataclass
class SandboxResult:
    """Execution output from an isolated sandbox run."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0
    failed_tests: List[str] = field(default_factory=list)
    error_summary: str = ""

    @property
    def is_success(self) -> bool:
        """True if the test suite passed with exit code 0."""
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class CodeSandboxPort(Protocol):
    """Port interface for executing generated tests in an isolated sandbox."""

    def execute(self, code: str) -> SandboxResult:
        """Executes candidate Python code containing tests."""
        ...
