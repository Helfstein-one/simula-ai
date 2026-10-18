# Technical Analysis & Implementation Blueprint: Code Parser & Pytest Sandbox (Milestone 2)

**Author:** Explorer 2 (`teamwork_preview_explorer_m2_2`)  
**Mission:** Design, verify, and specify concrete blueprints for `core/code_parser.py` and `core/sandbox.py`.  
**Date:** 2026-10-12  

---

## 1. Executive Summary & Problem Boundary

In Milestone 2 (CoALA Cognitive Loop & Sandbox), Simula-AI automates iterative code synthesis and validation using DeepSeek models via OpenRouter. This pipeline requires two mission-critical core components:

1. **`core/code_parser.py`**:
   - **Reasoning Tag Stripping**: DeepSeek R1 emits chain-of-thought tokens inside `<think>...</think>` tags. The parser must reliably strip these tags—including unclosed tags caused by context truncation—without discarding the candidate Python code.
   - **Markdown Code Block Extraction**: Isolates runnable Python blocks from mixed LLM output (explanations, YAML specs, bash snippets), handling varying fence tags (`python`, `py`, `python3`, or empty) and docstrings with embedded backticks.
   - **Pre-sandbox AST Verification**: Uses `ast.parse` to validate syntactic correctness before executing tests, providing line and column error diagnostics.

2. **`core/sandbox.py`**:
   - **Subprocess Isolation**: Executes `pytest` against an isolated temporary script named `simula_temp_test.py` located in an ephemeral `tempfile.TemporaryDirectory`.
   - **Security Guarantees**: Absolute **zero `eval()` / zero `exec()`** in the host Python process. Host environment variables are sanitized to prevent secret exfiltration (e.g., `OPENROUTER_API_KEY`).
   - **Timeout Enforcement**: Strict timeout (default 30s) killing hanging processes (e.g., infinite loops generating unique keys) and returning status flag `timed_out=True`.
   - **Failure & Traceback Extraction**: Captures `exit_code`, `stdout`, `stderr`, failed test function names, and creates concise failure summaries tailored for injection into CoALA's `episodic_memory`.

Both components were verified against all 8 target tests in `tests/e2e/test_tier1_features.py` and `tests/e2e/test_tier2_boundaries.py`, passing with **100% success**.

---

## 2. Component 1: `core/code_parser.py` Blueprint

### 2.1 Regex Tag Stripping Architecture

DeepSeek R1 output variations present several syntactic edge cases:
- Closed tags across multiple lines: `<think>\n...\n</think>`.
- Tags with HTML/XML attributes: `<think style="..." class="...">`.
- Tags with whitespace before the closing bracket: `</think >`.
- Unclosed `<think>` tags where the model truncated reasoning right before the code fence: `<think>\n...\n```python\n...`.
- Unclosed `<think>` tags with no code fence at all (prompt truncation).

#### Regex Specifications

```python
# 1. Closed think tags (non-greedy, case-insensitive, DOTALL)
THINK_TAG_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?</think\s*>",
    flags=re.DOTALL | re.IGNORECASE
)

# 2. Unclosed think tag followed by a markdown code block fence
UNCLOSED_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?(?=```)",
    flags=re.DOTALL | re.IGNORECASE
)

# 3. Unclosed think tag with no markdown fence (truncation at EOF)
UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*$",
    flags=re.DOTALL | re.IGNORECASE
)
```

#### Stripping Logic Flow

```python
@staticmethod
def strip_think_tags(text: str) -> str:
    if not text:
        return ""
    # Pass 1: Remove all matching closed <think>...</think> blocks
    cleaned = THINK_TAG_REGEX.sub("", text)
    # Pass 2: Check if an unclosed <think> remains
    if "<think" in cleaned.lower():
        if "```" in cleaned:
            # Strip reasoning up to the first code fence
            cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
        else:
            # Strip reasoning to end-of-string
            cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
    return cleaned.strip()
```

### 2.2 Markdown Code Block Extraction & Scoring

#### Fence Extraction Pattern
To avoid prematurely truncating on inline triple backticks inside docstrings (e.g. `"""contains ```triple ticks``` inside"""`), the closing fence must require its own line or end of text:

```python
CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)[^\n]*\n(.*?)\n[ \t]*```[ \t]*(?:\n|$)",
    flags=re.DOTALL
)

UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)[^\n]*\n(.*)$",
    flags=re.DOTALL
)
```

#### Selection & Prioritization Heuristic
When an LLM response contains multiple code fences (e.g. a small YAML schema snippet followed by the full Python test file):
1. **Filter**: Drop known non-Python languages (`bash`, `sh`, `yaml`, `yml`, `json`, `sql`, `html`, `css`, `markdown`, `text`) if other blocks exist.
2. **Score Candidate Blocks**:
   - `ast.parse` succeeds: **+5,000 points**
   - Contains test functions (`def test_`): **+2,000 points**
   - Contains imports (`import ` or `from `): **+1,000 points**
   - Contains function definitions (`def `): **+500 points**
   - Contains class definitions (`class `): **+200 points**
   - Body character length: **+len(body)** (prefers complete script over tiny stubs)
3. **Unclosed Fallback**: If no closed block matches, inspect unclosed fences (for truncated completions).
4. **Raw Code Fallback**: If no markdown fences are found, search for the first line starting with `import `, `from `, `def `, `class `, or `#!`.

### 2.3 Pre-sandbox AST Verification (`validate_syntax`)

Validates Python syntax in-memory before writing to disk or invoking pytest:
- Non-empty check: returns `(False, "Code is empty")` for blank inputs.
- `ast.parse(code)`:
  - If clean: returns `(True, None)`.
  - If `SyntaxError`: extracts `lineno`, `offset`, and `msg`, returning `(False, f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}")`.
  - Catches other parser exceptions cleanly without crashing.

### 2.4 Concrete Implementation: `core/code_parser.py`

```python
"""core/code_parser.py - Regex cleaning, fence extraction, and AST syntax validation."""

from __future__ import annotations

import ast
import re
from typing import Optional, Tuple, List

# Regex for stripping reasoning tags
THINK_TAG_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?</think\s*>",
    flags=re.DOTALL | re.IGNORECASE
)
UNCLOSED_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?(?=```)",
    flags=re.DOTALL | re.IGNORECASE
)
UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*$",
    flags=re.DOTALL | re.IGNORECASE
)

# Regex for extracting fenced code blocks
CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)[^\n]*\n(.*?)\n[ \t]*```[ \t]*(?:\n|$)",
    flags=re.DOTALL
)
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)[^\n]*\n(.*)$",
    flags=re.DOTALL
)

NON_PYTHON_LANGUAGES = {
    "bash", "sh", "zsh", "shell", "yaml", "yml", "json", "sql",
    "html", "xml", "css", "markdown", "md", "text", "txt", "diff"
}


class CodeParser:
    """Extracts, cleans, and validates executable Python code from LLM outputs."""

    @staticmethod
    def strip_think_tags(text: str) -> str:
        """Strip <think>...</think> tags, including unclosed tags using lookaheads."""
        if not text:
            return ""

        # Step 1: Strip standard closed think tags
        cleaned = THINK_TAG_REGEX.sub("", text)

        # Step 2: Handle unclosed think tag
        if "<think" in cleaned.lower():
            if "```" in cleaned:
                cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
            else:
                cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)

        return cleaned.strip()

    @classmethod
    def extract_python_code(cls, response_text: str) -> str:
        """Strip reasoning tags and extract the primary executable Python code block."""
        cleaned_text = cls.strip_think_tags(response_text)

        # Match closed code blocks
        matches = CODE_BLOCK_PATTERN.findall(cleaned_text)

        candidates: List[str] = []
        if matches:
            for lang, body in matches:
                lang_clean = lang.strip().lower()
                body_clean = body.strip()
                if not body_clean:
                    continue
                # Exclude explicit non-python blocks if alternatives exist
                if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:
                    continue
                candidates.append(body_clean)

        # Fallback to unclosed code block if truncated
        if not candidates:
            unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(cleaned_text)
            for lang, body in unclosed_matches:
                lang_clean = lang.strip().lower()
                body_clean = body.strip()
                if body_clean and lang_clean not in NON_PYTHON_LANGUAGES:
                    candidates.append(body_clean)

        if candidates:
            def _score_candidate(block: str) -> int:
                score = len(block)
                if "import " in block or "from " in block:
                    score += 1000
                if "def test_" in block:
                    score += 2000
                elif "def " in block:
                    score += 500
                if "class " in block:
                    score += 200
                try:
                    ast.parse(block)
                    score += 5000
                except SyntaxError:
                    pass
                return score

            return max(candidates, key=_score_candidate).strip()

        # Fallback: Raw un-fenced code
        lines = cleaned_text.splitlines()
        first_code_idx = -1
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "def ", "class ", "#!")):
                first_code_idx = idx
                break

        if first_code_idx != -1:
            return "\n".join(lines[first_code_idx:]).strip()

        return cleaned_text.strip()

    @staticmethod
    def validate_syntax(code: str) -> Tuple[bool, Optional[str]]:
        """Verify code syntax using ast.parse without executing it."""
        if not code or not code.strip():
            return False, "Code is empty"

        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        except Exception as e:
            return False, f"AST verification failed: {str(e)}"
```

---

## 3. Component 2: `core/sandbox.py` Blueprint

### 3.1 Subprocess Isolation Architecture

Executing untrusted, model-generated code in the host process introduces serious security and stability hazards (memory leaks, global namespace corruption, intentional or accidental disk wiping). 

To ensure airtight isolation:
1. **Zero `eval()` / Zero `exec()`**: All execution occurs via `subprocess.run` as a separate operating system process.
2. **Dedicated Temporary Directory**: `tempfile.TemporaryDirectory(prefix="simula_sandbox_")` is allocated per test run.
3. **Dedicated Target File**: Code is written strictly to `simula_temp_test.py` within the temporary directory.
4. **Guaranteed Cleanup**: The context manager cleans up the directory and all test artifacts upon completion or exception.
5. **Sanitized Environment**: Sensitive host environment variables (`OPENROUTER_API_KEY`, etc.) are stripped. The child process receives only:
   - `PATH`: System execution path.
   - `PYTHONPATH`: Clean path containing `temp_dir` and the project root.
   - `TMPDIR`: Set to `temp_dir`.
   - `LANG`: UTF-8 locale.
   - `PYTHONDONTWRITEBYTECODE`: Set to `"1"` (prevents `__pycache__` creation).
   - `VIRTUAL_ENV`: Inherited if currently active to access virtual environment packages (`faker`, `pytest`, `pandas`, etc.).

### 3.2 Subprocess Command Configuration

The test runner invokes:
```python
cmd = [
    sys.executable,
    "-m", "pytest",
    "simula_temp_test.py",
    "-v",
    "--tb=short",
    "-p", "no:cacheprovider"
]
```
- `sys.executable -m pytest`: Guarantees pytest runs with the exact Python interpreter and installed virtualenv packages.
- `-v`: Verbose reporting of each test outcome (`simula_temp_test.py::test_name PASSED/FAILED`).
- `--tb=short`: Concise tracebacks containing only the offending line and assertion values (optimal for LLM context windows).
- `-p no:cacheprovider`: Disables `.pytest_cache` generation, avoiding disk writes in temp dirs.

### 3.3 Strict Timeout Enforcement

Infinite loops (e.g. `while True` trying to resolve impossible uniqueness constraints) are stopped by passing `timeout=self.timeout_seconds` to `subprocess.run`.
- Catching `subprocess.TimeoutExpired`:
  - Decodes partial `stdout`/`stderr` (`bytes` or `str`).
  - Sets `exit_code = -1`.
  - Sets `timed_out = True`.
  - Sets `failed_tests = ["TIMEOUT"]`.
  - Sets `error_summary = f"Execution timed out after {self.timeout_seconds} seconds."`.
  - `is_success` property evaluates to `False`.

### 3.4 Traceback Extraction & Episodic Memory Summarization

#### Extracted Artifacts:
1. **`failed_tests: List[str]`**:
   Extracted from lines matching `simula_temp_test.py::<test_name> FAILED` and `FAILED simula_temp_test.py::<test_name>`.
2. **`error_summary: str`**:
   - Isolates the `=== FAILURES ===` or `=== ERRORS ===` block.
   - Truncates to the first 50 lines / ~2,000 characters to prevent prompt bloat while preserving the exact failing assertion, line number, and exception message.
3. **`format_episodic_feedback(result: SandboxResult) -> str`**:
   Utility formatting the failure into a markdown block for injection into `episodic_memory` and subsequent LLM prompt turns.

### 3.5 Concrete Implementation: `core/sandbox.py`

```python
"""core/sandbox.py - Isolated subprocess Pytest execution sandbox."""

from __future__ import annotations

import os
import re
import sys
import time
import tempfile
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional


@dataclass
class SandboxResult:
    """Structured result from a Pytest sandbox execution."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0
    failed_tests: List[str] = field(default_factory=list)
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

    def __init__(self, timeout_seconds: int = 30):
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
                "-m", "pytest",
                "simula_temp_test.py",
                "-v",
                "--tb=short",
                "-p", "no:cacheprovider"
            ]

            timed_out = False
            try:
                res = subprocess.run(
                    cmd,
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env
                )
                stdout = res.stdout or ""
                stderr = res.stderr or ""
                exit_code = res.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = -1
                stdout = self._decode_stream(exc.stdout)
                stderr = self._decode_stream(exc.stderr) or f"Execution timed out after {self.timeout_seconds} seconds."
            except Exception as exc:
                exit_code = -2
                stdout = ""
                stderr = f"Subprocess invocation failure: {str(exc)}"

            duration = time.time() - t0
            failed_tests, error_summary = self._parse_failures(stdout, stderr, exit_code, timed_out)

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
    def _decode_stream(stream: Optional[object]) -> str:
        if stream is None:
            return ""
        if isinstance(stream, bytes):
            return stream.decode("utf-8", errors="replace")
        return str(stream)

    def _parse_failures(
        self, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> Tuple[List[str], str]:
        """Extract failed test names and format a concise failure traceback."""
        if exit_code == 0 and not timed_out:
            return [], ""

        if timed_out:
            return ["TIMEOUT"], f"Execution timed out after {self.timeout_seconds} seconds."

        failed_tests: List[str] = []
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
        summary_lines: List[str] = []
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
```

---

## 4. Integration with CoALA Cognitive Loop

The interaction between `CodeParser`, `PytestSandbox`, and `core/graph.py` operates as follows:

```
[OpenRouter R1 Completion]
          │
          ▼
CodeParser.strip_think_tags()
          │
          ▼
CodeParser.extract_python_code()
          │
          ▼
CodeParser.validate_syntax()
   ├── [SyntaxError] ──► Inject directly into episodic_memory & trigger retry
   └── [Valid AST]   ──► Proceed to PytestSandbox
                                │
                                ▼
                       PytestSandbox.execute(code)
                                │
                                ├── [exit_code == 0]  ──► Status: SUCCESS ──► End Loop
                                └── [exit_code != 0]  ──► SandboxResult.format_episodic_feedback()
                                                                │
                                                                ▼
                                                        Append to episodic_memory
                                                                │
                                                                ▼
                                                        Route to node_generate (retry)
```

In `node_generate`:
```python
raw_response = llm_client.generate_candidate(...)
code = CodeParser.extract_python_code(raw_response)
is_valid, err = CodeParser.validate_syntax(code)
# Updates state["working_memory"]["generated_code"] = code
```

In `node_execute`:
```python
result = sandbox.execute(code)
if result.is_success:
    state["status"] = "SUCCESS"
else:
    record = {
        "iteration": state["iterations"],
        "generated_code": code,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "error_summary": result.error_summary,
        "failed_tests": result.failed_tests,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    state["episodic_memory"].append(record)
    state["status"] = "RETRY" if state["iterations"] < state["max_iterations"] else "FAILED_MAX_RETRIES"
```

---

## 5. Verification Evidence & E2E Test Compatibility

### 5.1 Verification Against Requirements & E2E Test Suite

Both modules were verified against the 8 tests across `tests/e2e/test_tier1_features.py` and `tests/e2e/test_tier2_boundaries.py`:

| Test Name | Target Requirement | Prototype Result | Verified Behavior |
|---|---|---|---|
| `test_r1_regex_think_tag_stripping` | R1 Acceptance | **PASSED** | Strips `<think>...</think>`, preserves code fence. |
| `test_r1_ast_code_extraction_and_syntax_validation` | R1 AST check | **PASSED** | Extracts `def test_mesh_success()`, `validate_syntax` returns `(True, None)`. |
| `test_r1_subprocess_sandbox_isolated_execution` | R1 Sandbox | **PASSED** | Pytest executes in temp directory, returns `exit_code == 0`, `is_success == True`. |
| `test_t2_unclosed_think_tag_before_code_fence` | R1 / Boundary | **PASSED** | Strips truncated `<think>` before ` ```python `, valid AST syntax. |
| `test_t2_unclosed_think_tag_without_any_code_fence` | Boundary | **PASSED** | Strips unclosed `<think>` with no fences cleanly. |
| `test_t2_sandbox_handles_assertion_failure_exit_code_1` | Boundary | **PASSED** | Captures `exit_code == 1`, extracts `test_failing_assertion` into `failed_tests`. |
| `test_t2_sandbox_handles_syntax_error_exit_code_2` | Boundary | **PASSED** | Captures exit code 2, extracts `SyntaxError` from stdout/stderr. |
| `test_t2_sandbox_timeout_expiration` | R1 Acceptance | **PASSED** | Kills hanging loop at 2s, sets `timed_out == True`, `exit_code == -1`. |

### 5.2 Unit Test Blueprint (`tests/unit/`)

To complement the E2E tests, the implementers should add dedicated unit tests:

#### File: `tests/unit/test_code_parser.py`
- `test_strip_closed_tags`: standard reasoning blocks.
- `test_strip_unclosed_lookahead`: unclosed reasoning prior to markdown block.
- `test_strip_case_insensitive`: `<THINK>...</THINK>` and `<Think>`.
- `test_extract_python_prefers_test_functions`: selects candidate block with assertions over stubs.
- `test_extract_python_nested_docstring_ticks`: ensures triple ticks inside docstrings are not split.
- `test_extract_python_unclosed_fence`: handles LLM token exhaustion mid-code.
- `test_validate_syntax_errors`: verifies line numbers on invalid syntax.

#### File: `tests/unit/test_sandbox.py`
- `test_sandbox_zero_eval`: mocks `builtins.eval` and `builtins.exec` to assert zero calls in host process.
- `test_sandbox_temp_dir_lifecycle`: confirms temporary directory does not exist after `execute()`.
- `test_sandbox_secret_isolation`: asserts `OPENROUTER_API_KEY` is not visible inside the child process.
- `test_sandbox_timeout_recovery`: verifies process termination and prompt summary on timeout.

---

## 6. Failure Modes, Edge Cases, and Mitigations Matrix

| Failure Mode | Root Cause | Impact | Mitigation Strategy |
|---|---|---|---|
| **Truncated `<think>` tag** | DeepSeek R1 context limit hit during reasoning | Parser drops entire code block or leaves unclosed tag | Regex lookahead to ` ``` ` code fence boundary strips reasoning while preserving code. |
| **Docstrings with triple backticks** | Generated docstrings or markdown examples containing ` ``` ` | Regex stops prematurely | Closing fence regex strictly matches `\n[ \t]*```[ \t]*(?:\n|$)` on its own line. |
| **Infinite loop in generator** | Generator `while` loop cannot satisfy strict relational constraint | Process hangs indefinitely | `subprocess.run(timeout=30)` terminates child process and flags `timed_out=True`. |
| **Host process pollution** | Code calling `sys.exit()` or mutating global state | Crashes CLI / UI | Zero `eval()` / zero `exec()`; isolated execution in separate OS process. |
| **Environment secret leakage** | Generated code reading `os.environ` | Exfiltration of `OPENROUTER_API_KEY` | Sanitized environment dictionary passed to subprocess without sensitive keys. |
| **No tests collected** | Generator script lacks `test_*` functions | Pytest exit code 5 | Detected and reported with actionable guidance in `error_summary`. |
| **Subprocess zombie processes** | Process times out | Resource leak | Context manager cleans temp directory; `subprocess.run` kills subprocess on `TimeoutExpired`. |
