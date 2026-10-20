"""adapters/outbound/podman_sandbox_adapter.py - Podman container sandbox with auto-fallback."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from adapters.outbound.pytest_sandbox_adapter import PytestSandboxAdapter
from application.ports.sandbox_port import CodeSandboxPort, SandboxResult

logger = logging.getLogger("simula.sandbox.podman")


class PodmanSandboxAdapter(CodeSandboxPort):
    """Executes test suites inside isolated rootless Podman containers.
    
    Provides transparent automatic fallback to PytestSandboxAdapter (subprocess)
    when Podman is not installed, daemon is not running, or container launch fails.
    """

    def __init__(
        self,
        container_image: str = "python:3.12-slim",
        timeout_seconds: int = 30,
        fallback_sandbox: Optional[CodeSandboxPort] = None,
    ) -> None:
        self.container_image = container_image
        self.timeout_seconds = timeout_seconds
        self.fallback_sandbox = fallback_sandbox or PytestSandboxAdapter(timeout_seconds=timeout_seconds)

    @classmethod
    def is_podman_available(cls) -> bool:
        """Checks if the podman executable is present and container engine is responsive."""
        podman_path = shutil.which("podman")
        if not podman_path:
            return False
        try:
            res = subprocess.run(
                ["podman", "info"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute(self, code: str) -> SandboxResult:
        """Executes test code in a Podman container, falling back to subprocess if unavailable."""
        if not self.is_podman_available():
            logger.info("Podman unavailable or machine not running. Falling back to isolated subprocess sandbox.")
            return self.fallback_sandbox.execute(code)

        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="simula_podman_") as tmp_dir:
            test_file = Path(tmp_dir) / "simula_temp_test.py"
            test_file.write_text(code, encoding="utf-8")

            # Command running pytest inside container
            cmd = [
                "podman",
                "run",
                "--rm",
                "-v",
                f"{tmp_dir}:/workspace:Z",
                "-w",
                "/workspace",
                self.container_image,
                "pytest",
                "simula_temp_test.py",
                "-v",
                "--tb=short",
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
                if proc.returncode == 125:
                    logger.warning("Podman returned error 125 (daemon/engine error). Falling back to subprocess.")
                    return self.fallback_sandbox.execute(code)

                duration = time.time() - t0
                return SandboxResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    timed_out=False,
                    duration_seconds=duration,
                    failed_tests=[],
                    error_summary=proc.stderr or (proc.stdout[:500] if proc.returncode != 0 else ""),
                )
            except subprocess.TimeoutExpired:
                duration = time.time() - t0
                return SandboxResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"Podman execution timed out after {self.timeout_seconds}s",
                    timed_out=True,
                    duration_seconds=duration,
                    error_summary="Container execution timed out",
                )
            except Exception as e:
                logger.warning("Podman container execution failed: %s. Using subprocess fallback.", e)
                return self.fallback_sandbox.execute(code)
