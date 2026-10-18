"""core/sandbox.py - Isolated subprocess Pytest execution sandbox."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxResult:
    """Structured result from a Pytest sandbox execution."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0
    failed_tests: list[str] = field(default_factory=list)
    error_summary: str = ""

    @property
    def is_success(self) -> bool:
        """Execution succeeded if pytest returned 0 and did not time out."""
        return self.exit_code == 0 and not self.timed_out

    def format_episodic_feedback(self) -> str:
        """Format test results into a concise markdown summary for CoALA episodic memory."""
        if self.is_success:
            return "All tests passed successfully (Exit code: 0)."

        if self.timed_out:
            return (
                f"EXECUTION TIMED OUT after {self.duration_seconds:.1f}s.\n"
                "Possible infinite loop in data generation (e.g. while loop generating unique keys)."
            )

        failed_str = ", ".join(self.failed_tests) if self.failed_tests else "Unknown failure"
        return (
            f"Pytest failed with exit code {self.exit_code}.\n"
            f"Failed tests: {failed_str}\n\n"
            f"Traceback Summary:\n{self.error_summary}"
        )


class PytestSandbox:
    """Executes generated Python test suites in an isolated temporary subprocess."""

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(self, code: str) -> SandboxResult:
        """Write code to simula_temp_test.py in an isolated directory and execute pytest via subprocess."""
        t0 = time.time()

        with tempfile.TemporaryDirectory(prefix="simula_sandbox_") as tmp_dir:
            test_file = Path(tmp_dir) / "simula_temp_test.py"
            test_file.write_text(code, encoding="utf-8")

            # Prepare sanitized environment
            env = {
                "PATH": os.environ.get("PATH", ""),
                "LANG": os.environ.get("LANG", "en_US.UTF-8"),
                "TMPDIR": tmp_dir,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if "VIRTUAL_ENV" in os.environ:
                env["VIRTUAL_ENV"] = os.environ["VIRTUAL_ENV"]

            # Preserve project root in PYTHONPATH for local imports if needed
            cwd_path = str(Path.cwd().resolve())
            existing_pp = os.environ.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{tmp_dir}:{cwd_path}:{existing_pp}".strip(":")

            cmd = [
                sys.executable,
                "-m",
                "pytest",
                "simula_temp_test.py",
                "-v",
                "--tb=short",
                "-p",
                "no:cacheprovider",
            ]

            timed_out = False
            try:
                res = subprocess.run(
                    cmd,
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                    check=False,
                )
                stdout = res.stdout or ""
                stderr = res.stderr or ""
                exit_code = res.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = -1
                stdout = self._decode_stream(exc.stdout)
                stderr = (
                    self._decode_stream(exc.stderr)
                    or f"Execution timed out after {self.timeout_seconds} seconds."
                )
            except (OSError, ValueError) as exc:
                exit_code = -2
                stdout = ""
                stderr = f"Subprocess invocation failure: {exc!s}"

            duration = time.time() - t0
            failed_tests, error_summary = self._parse_failures(
                stdout, stderr, exit_code, timed_out
            )

            return SandboxResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                duration_seconds=duration,
                failed_tests=failed_tests,
                error_summary=error_summary,
            )

    @staticmethod
    def _decode_stream(stream: object | None) -> str:
        if stream is None:
            return ""
        if isinstance(stream, bytes):
            return stream.decode("utf-8", errors="replace")
        return str(stream)

    def _parse_failures(
        self, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> tuple[list[str], str]:
        """Extract failed test names and format a concise failure traceback."""
        if exit_code == 0 and not timed_out:
            return [], ""

        if timed_out:
            return (
                ["TIMEOUT"],
                f"Execution timed out after {self.timeout_seconds} seconds.",
            )

        failed_tests: list[str] = []
        for line in stdout.splitlines():
            line_clean = line.strip()
            # Match verbose pytest failure output line
            m1 = re.search(r"simula_temp_test\.py::(\w+)\s+FAILED", line_clean)
            if m1 and m1.group(1) not in failed_tests:
                failed_tests.append(m1.group(1))

            # Match short test summary line
            m2 = re.match(r"FAILED\s+simula_temp_test\.py::(\w+)", line_clean)
            if m2 and m2.group(1) not in failed_tests:
                failed_tests.append(m2.group(1))

        if exit_code == 5 and not failed_tests:
            return [], "Pytest exit code 5: No tests collected. Ensure test functions start with 'test_'."

        # Extract failure / error traceback section
        summary_lines: list[str] = []
        capture = False
        for line in stdout.splitlines():
            if any(marker in line for marker in ("=== FAILURES ===", "=== ERRORS ===")):
                capture = True
            if capture:
                summary_lines.append(line)

        if summary_lines:
            summary = "\n".join(summary_lines[:50]).strip()
        else:
            summary = (stderr.strip() or stdout.strip())[:1500]

        return failed_tests, summary
