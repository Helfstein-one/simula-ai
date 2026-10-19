"""adapters/outbound/pytest_sandbox_adapter.py - Adapter for isolated subprocess Pytest execution."""

from __future__ import annotations

from application.ports.sandbox_port import CodeSandboxPort, SandboxResult
from core.sandbox import PytestSandbox


class PytestSandboxAdapter(CodeSandboxPort):
    """Adapter executing tests via PytestSandbox in isolated subprocess."""

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.sandbox = PytestSandbox(timeout_seconds=timeout_seconds)

    def execute(self, code: str) -> SandboxResult:
        """Executes candidate code in temporary subprocess sandbox and maps result."""
        res = self.sandbox.execute(code)
        return SandboxResult(
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            timed_out=res.timed_out,
            duration_seconds=res.duration_seconds,
            failed_tests=res.failed_tests,
            error_summary=res.error_summary,
        )
