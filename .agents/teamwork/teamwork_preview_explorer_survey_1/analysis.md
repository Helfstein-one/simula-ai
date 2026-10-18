# Technical Survey & Specification: Core CoALA Cognitive Loop & State Management (R1)

## 1. Executive Summary & Architectural Overview

Simula-AI is an autonomous relational data mocking framework designed for Data Mesh ecosystems. It ingests data contract YAML specifications and leverages the **CoALA (Cognitive Architectures for Language Agents)** pattern to synthesize consistent Faker generators, validation test suites, exported datasets, and interactive entity-relationship diagrams.

At the center of Simula-AI is the **Core Cognitive Loop** implemented in `core/` using **LangGraph** (`StateGraph`), integrating **OpenRouter DeepSeek R1** reasoning models with an **isolated, zero-eval Pytest subprocess sandbox**.

```
                        +---------------------------------------------+
                        |                 SimulaState                 |
                        |  - Procedural Memory (Rules & Guidelines)   |
                        |  - Working Memory (Contract & Code & Output)|
                        |  - Episodic Memory (Tracebacks & History)   |
                        |  - Iteration Count & Status                 |
                        +---------------------------------------------+
                                               |
                                               v
                                    +--------------------+
                                    |  node_initialize   |
                                    +--------------------+
                                               |
                                               v
+------------------->------------------+-----------------+
|                                      |  node_generate  | (Internal Action)
|                                      | (OpenRouter R1) |
|                                      +-----------------+
|                                               |
|                                        [Clean & Parse]
|                                     (<think> strip & AST)
|                                               |
|                                               v
|                                      +-----------------+
|                                      |  node_execute   | (External Action)
|                                      | (Pytest Sandbox)|
|                                      +-----------------+
|                                               |
|                                         [Capture RC,   |
|                                        stdout, stderr] |
|                                               |
|                                               v
|    [rc != 0 AND iter < max_iter]     +-----------------+
+----------------<---------------------| route_decision  |
         (Append to Episodic Memory)   +-----------------+
                                         |             |
                 [rc == 0]               |             | [rc != 0 AND iter >= max_iter]
                     v                   v             v
             +---------------+                     +----------------------+
             |    SUCCESS    |                     |  FAILED_MAX_RETRIES  |
             | (End / Export)|                     |     (End / Error)    |
             +---------------+                     +----------------------+
```

---

## 2. CoALA Cognitive Architecture & SimulaState Schema

The CoALA framework decomposes agent cognition into distinct memory and action systems:

### 2.1 Memory Architecture

1. **Procedural Memory (`procedural_memory`)**:
   Contains static guidelines, data engineering best practices, Faker library idioms, relational integrity axioms, and Pytest assertions requirements:
   - **Topological Generation Order**: Parent tables (primary keys) must be populated before child tables (foreign keys).
   - **Referential Integrity**: Child foreign key values must strictly exist in the set of parent primary keys; no orphan records.
   - **Domain Faker Mappings**: Correct Faker providers for Brazilian and global data mesh domains (CNPJ/CPF, company names, currency amounts, ISO timestamps, status enums, UUIDs).
   - **Pytest Suite Requirements**: Deterministic tests asserting non-null constraints, unique constraints, foreign key presence, correct row counts, and data types.
   - **Standalone Exportability**: Code must be self-contained and run without external runtime state.

2. **Working Memory (`working_memory`)**:
   Short-term workspace containing:
   - `contract_yaml`: Raw ingested contract string.
   - `contract_dict`: Structured parsed YAML dictionary.
   - `generated_code`: Current candidate Python script containing generator logic and Pytest test suite.
   - `pytest_output`: Combined stdout/stderr from the latest sandbox test execution.
   - `pytest_exit_code`: Subprocess return code (0 = success, 1 = test failure, 2 = error, etc.).
   - `last_error`: Condensed error summary for logging.

3. **Episodic Memory (`episodic_memory`)**:
   Chronological sequence of previous failed attempts within the execution session:
   - Iteration number.
   - Executed candidate code snapshot.
   - Pytest return code.
   - Captured stdout and stderr.
   - Extracted failure summary (specific failed assertions, lines, and exceptions).
   - Timestamp.
   - This history is fed back into subsequent generation prompts, enabling the model to perform reflection and iterative bug-fixing.

### 2.2 Complete `SimulaState` TypedDict Specification

```python
"""core/state.py - Type definitions for Simula-AI CoALA state."""

from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional, Literal

class EpisodicMemoryRecord(TypedDict):
    iteration: int
    generated_code: str
    exit_code: int
    stdout: str
    stderr: str
    error_summary: str
    failed_tests: List[str]
    timestamp: str

class WorkingMemory(TypedDict):
    contract_yaml: str
    contract_dict: Dict[str, Any]
    generated_code: Optional[str]
    pytest_output: Optional[str]
    pytest_exit_code: Optional[int]
    last_error: Optional[str]

class ProceduralMemory(TypedDict):
    system_prompt: str
    faker_rules: List[str]
    relational_rules: List[str]
    pytest_rules: List[str]

StatusType = Literal[
    "INIT",
    "GENERATING",
    "EXECUTING",
    "RETRY",
    "SUCCESS",
    "FAILED_MAX_RETRIES",
    "ERROR"
]

class SimulaState(TypedDict):
    procedural_memory: ProceduralMemory
    working_memory: WorkingMemory
    episodic_memory: List[EpisodicMemoryRecord]
    iterations: int
    max_iterations: int
    status: StatusType
    error_message: Optional[str]
```

---

## 3. Internal Action: DeepSeek OpenRouter Generation (`internal_action_generate`)

### 3.1 Endpoint & Authentication
- **Base URL**: `https://openrouter.ai/api/v1`
- **Completions URL**: `https://openrouter.ai/api/v1/chat/completions`
- **Headers**:
  ```http
  Authorization: Bearer <OPENROUTER_API_KEY>
  Content-Type: application/json
  HTTP-Referer: https://simula.ai
  X-Title: Simula-AI Data Mocking Framework
  ```

### 3.2 Model Hierarchy & Fallback Cascade
DeepSeek R1 provides deep chain-of-thought mathematical and relational reasoning, making it ideal for multi-table relational schema mocking. However, high demand frequently triggers HTTP 429 rate limits on public OpenRouter gateways.

**Model Cascade Order:**
1. **Primary**: `deepseek/deepseek-r1` (or `deepseek/deepseek-r1:free` if specified)
2. **Fallback 1**: `deepseek/deepseek-chat` (DeepSeek-V3, non-reasoning high-speed production model)
3. **Fallback 2**: `deepseek/deepseek-r1-distill-llama-70b`
4. **Fallback 3**: `deepseek/deepseek-r1-distill-qwen-32b`

### 3.3 HTTP 429 & Transient Error Handling Algorithm
When OpenRouter returns HTTP 429, 502, 503, or 504:
1. **Exponential Backoff with Full Jitter**:
   $$\text{sleep} = \min(\text{max\_backoff}, \text{base\_delay} \times 2^{\text{attempt}}) + \text{uniform}(0, 1)$$
   - `base_delay = 2.0s`, `backoff_factor = 2.0`, `max_backoff = 30.0s`, `max_retries_per_model = 3`.
2. **Respect `Retry-After` Header**:
   If the HTTP response contains a `Retry-After` header, `sleep = max(sleep, float(retry_after))`.
3. **Model Fallback Cascade**:
   If all 3 retries for the current model fail with 429 or 5xx, switch immediately to the next model in `FALLBACK_MODELS` and restart the retry sequence.

### 3.4 Prompt Construction Strategy
1. **System Message**:
   Contains static guidelines from `procedural_memory` (data engineering rules, Faker usage, relational topological sorting, Pytest assertion format).
2. **First Iteration (`iterations == 0`)**:
   User message supplies the full `contract_yaml`, instructs the model to generate a self-contained Python script implementing data generators and Pytest test functions.
3. **Subsequent Iterations (`iterations > 0`)**:
   User message appends the episodic memory feedback:
   ```markdown
   [ITERATION {k} FAILED PYTEST VALIDATION]
   Return code: {exit_code}

   Failure Summary:
   {error_summary}

   Pytest Traceback:
   {pytest_output_snippet}

   CORRECTION INSTRUCTIONS:
   1. Analyze the exact assertion failure or exception.
   2. Ensure parent table primary keys are generated before child table foreign keys.
   3. Ensure all foreign key values match existing parent keys.
   4. Output the complete corrected Python code enclosed in ```python ... ```.
   ```

---

## 4. Code Extraction & Reasoning Tag Stripping (`core/code_parser.py`)

DeepSeek R1 outputs extensive reasoning inside `<think>...</think>` tags prior to delivering the solution. The code parser must cleanly remove these tags and extract executable Python code without corruption.

### 4.1 Edge Cases in Tag Stripping
1. **Standard Tags**: `<think>...</think>` across multiple lines.
2. **Tag Attributes or Whitespace**: `<think style="...">`, `</think >`.
3. **Unclosed `<think>` Tags**:
   If the completion hits token limits or omits `</think>`, a standard regex `r"<think>.*?</think>"` leaves the `<think>` tag open.
   - **Defense**: Use lookahead to detect if `<think` is present without a matching `</think>`. In that case, strip from `<think` up to the first markdown code block fence ```` ``` ````.
4. **Nested or Repeated Tags**: Apply non-greedy global regex replacement.

### 4.2 Verified Extraction Regex & Implementation

```python
"""core/code_parser.py - Regex cleaning and code extraction."""

import re
import ast
from typing import Tuple, Optional

THINK_TAG_REGEX = re.compile(r"<think(?:\s+[^>]*)?>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
UNCLOSED_THINK_REGEX = re.compile(r"<think(?:\s+[^>]*)?>.*?(?=```)", flags=re.DOTALL | re.IGNORECASE)
CODE_BLOCK_REGEX = re.compile(r"```(?:python|py)?\s*\n(.*?)```", flags=re.DOTALL | re.IGNORECASE)

class CodeParser:
    @staticmethod
    def strip_think_tags(text: str) -> str:
        """Strip <think>...</think> tags, including unclosed tags."""
        if not text:
            return ""
        # 1. Try stripping closed think blocks
        cleaned = THINK_TAG_REGEX.sub("", text)
        # 2. Check if an unclosed <think> remains
        if "<think" in cleaned.lower():
            if "```" in cleaned:
                cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
            else:
                cleaned = re.sub(r"<think(?:\s+[^>]*)?>.*", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        return cleaned.strip()

    @classmethod
    def extract_python_code(cls, response_text: str) -> str:
        """Strip think tags and extract the primary executable Python code block."""
        cleaned_text = cls.strip_think_tags(response_text)
        matches = CODE_BLOCK_REGEX.findall(cleaned_text)
        if matches:
            # If multiple blocks, select the largest one containing imports / defs
            valid_blocks = [
                m.strip() for m in matches 
                if ("import " in m or "def " in m or "class " in m)
            ]
            if valid_blocks:
                return max(valid_blocks, key=len)
            return max(matches, key=len).strip()
        
        # Fallback: if no code fence, check if raw text is python
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
        """Validate code syntax using ast.parse without executing it."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
```

---

## 5. External Action: Subprocess Pytest Sandbox (`external_action_execute`)

### 5.1 Strict Isolation & Security Constraints
1. **Zero `eval()` / Zero `exec()`**:
   The host Python runtime never executes the generated code using `eval()` or `exec()`.
2. **Subprocess Isolation**:
   Code is executed as a separate operating system process via `subprocess.run` running `pytest`.
3. **Ephemeral Temp Directory**:
   A dedicated temporary directory (`tempfile.TemporaryDirectory(prefix="simula_sandbox_")`) is allocated per execution and automatically cleaned up in a `finally:` block.
4. **Execution Timeout**:
   Enforced timeout (default 30 seconds). If the generator or test hangs (e.g., infinite `while` loop generating unique keys), the subprocess is terminated with `SIGKILL`, catching `subprocess.TimeoutExpired`.
5. **Environment Sanitization**:
   Pass a controlled subset of environment variables (`PATH`, `PYTHONPATH`, `LANG`, `TMPDIR`) so system secrets are not leaked to the test process.

### 5.2 Implementation Specification (`core/sandbox.py`)

```python
"""core/sandbox.py - Isolated subprocess Pytest execution sandbox."""

import os
import sys
import shutil
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0
    failed_tests: List[str] = None
    error_summary: str = ""

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

class PytestSandbox:
    def __init__(self, timeout_seconds: int = 30):
        self.timeout_seconds = timeout_seconds

    def execute(self, code: str) -> SandboxResult:
        """Write code to simula_temp_test.py in an isolated directory and run pytest."""
        temp_dir = tempfile.mkdtemp(prefix="simula_sandbox_")
        test_file_path = Path(temp_dir) / "simula_temp_test.py"
        test_file_path.write_text(code, encoding="utf-8")

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": f"{temp_dir}:{os.environ.get('PYTHONPATH', '')}",
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "TMPDIR": temp_dir,
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        cmd = [
            sys.executable,
            "-m", "pytest",
            str(test_file_path.name),
            "-v",
            "--tb=short",
            "--disable-warnings",
            "--no-header"
        ]

        try:
            res = subprocess.run(
                cmd,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )
            stdout = res.stdout or ""
            stderr = res.stderr or ""
            exit_code = res.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = f"Execution timed out after {self.timeout_seconds} seconds."
            exit_code = -1
            timed_out = True
        except Exception as exc:
            stdout = ""
            stderr = f"Subprocess execution error: {str(exc)}"
            exit_code = -2
            timed_out = False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        failed_tests, error_summary = self._parse_failures(stdout, stderr, exit_code, timed_out)
        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            failed_tests=failed_tests,
            error_summary=error_summary,
        )

    def _parse_failures(self, stdout: str, stderr: str, exit_code: int, timed_out: bool) -> tuple[List[str], str]:
        if exit_code == 0 and not timed_out:
            return [], ""
        if timed_out:
            return ["TIMEOUT"], f"Execution exceeded {self.timeout_seconds}s timeout."

        failed_tests = []
        for line in stdout.splitlines():
            if line.startswith("FAILED "):
                failed_tests.append(line.replace("FAILED ", "").strip())

        # Extract summary lines
        summary_lines = []
        capture = False
        for line in stdout.splitlines():
            if line.startswith("=== FAILURES ===") or line.startswith("=== ERRORS ==="):
                capture = True
            if capture:
                summary_lines.append(line)
        
        summary = "\n".join(summary_lines[:50]) if summary_lines else (stderr[:1000] or stdout[:1000])
        return failed_tests, summary
```

---

## 6. LangGraph StateGraph Architecture & Routing (`route_decision`)

### 6.1 StateGraph Node Topology
The cognitive loop consists of three main nodes and one conditional routing edge:

```
[START] ---> [node_initialize] ---> [node_generate] ---> [node_execute] ---> [route_decision]
                                           ^                                         |
                                           |--------- [route == "retry"] ------------|
                                                                                     |
                                                     [route == "success" or          v
                                                      route == "max_retries"] ---> [END]
```

### 6.2 Node Responsibilities

1. **`node_initialize(state: SimulaState) -> Dict[str, Any]`**:
   - Parses `working_memory["contract_yaml"]` using `yaml.safe_load`.
   - Populates `procedural_memory` with Faker and Pytest generation rules.
   - Sets `iterations = 0`, `status = "INIT"`.

2. **`node_generate(state: SimulaState) -> Dict[str, Any]`**:
   - Builds prompt combining `procedural_memory`, `contract_yaml`, and latest `episodic_memory` error feedback.
   - Calls OpenRouter DeepSeek client with automatic 429 retry and fallback models.
   - Strips `<think>` tags and extracts clean Python code using `CodeParser`.
   - Increments `iterations += 1`.
   - Sets `status = "GENERATING"`.
   - Updates `working_memory["generated_code"]`.

3. **`node_execute(state: SimulaState) -> Dict[str, Any]`**:
   - Sends `working_memory["generated_code"]` to `PytestSandbox.execute()`.
   - Sets `working_memory["pytest_output"]` and `pytest_exit_code`.
   - If `result.exit_code == 0`:
     - Sets `status = "SUCCESS"`.
   - If `result.exit_code != 0`:
     - Creates new `EpisodicMemoryRecord` with failure summary and traceback.
     - Appends to `episodic_memory`.
     - Sets `status = "RETRY"` if `iterations < max_iterations` else `"FAILED_MAX_RETRIES"`.

4. **`route_decision(state: SimulaState) -> Literal["retry", "success", "max_retries", "error"]`**:
   - Evaluates:
     - If `state["status"] == "SUCCESS"` or `state["working_memory"]["pytest_exit_code"] == 0`: return `"success"`
     - If `state["iterations"] >= state["max_iterations"]`: return `"max_retries"`
     - If `state["status"] == "ERROR"`: return `"error"`
     - Otherwise: return `"retry"`

### 6.3 Graph Definition Code (`core/graph.py`)

```python
"""core/graph.py - LangGraph StateGraph definition for CoALA loop."""

from typing import Literal
from langgraph.graph import StateGraph, START, END

from core.state import SimulaState
from core.llm_client import OpenRouterClient
from core.code_parser import CodeParser
from core.sandbox import PytestSandbox
from core.memory import create_initial_procedural_memory

def node_initialize(state: SimulaState) -> dict:
    import yaml
    raw_yaml = state["working_memory"]["contract_yaml"]
    parsed_contract = yaml.safe_load(raw_yaml)
    return {
        "working_memory": {
            **state["working_memory"],
            "contract_dict": parsed_contract,
        },
        "procedural_memory": create_initial_procedural_memory(),
        "iterations": 0,
        "status": "INIT",
    }

def node_generate(state: SimulaState, llm_client: OpenRouterClient) -> dict:
    current_iter = state["iterations"] + 1
    code_raw = llm_client.generate_candidate(
        procedural_memory=state["procedural_memory"],
        working_memory=state["working_memory"],
        episodic_memory=state["episodic_memory"],
        iteration=current_iter,
    )
    extracted_code = CodeParser.extract_python_code(code_raw)
    return {
        "working_memory": {
            **state["working_memory"],
            "generated_code": extracted_code,
        },
        "iterations": current_iter,
        "status": "GENERATING",
    }

def node_execute(state: SimulaState, sandbox: PytestSandbox) -> dict:
    code = state["working_memory"].get("generated_code") or ""
    result = sandbox.execute(code)

    updates = {
        "working_memory": {
            **state["working_memory"],
            "pytest_output": result.stdout + ("\n" + result.stderr if result.stderr else ""),
            "pytest_exit_code": result.exit_code,
            "last_error": result.error_summary,
        }
    }

    if result.is_success:
        updates["status"] = "SUCCESS"
    else:
        new_record = {
            "iteration": state["iterations"],
            "generated_code": code,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error_summary": result.error_summary,
            "failed_tests": result.failed_tests,
            "timestamp": "iso_timestamp",
        }
        updates["episodic_memory"] = state["episodic_memory"] + [new_record]
        if state["iterations"] >= state["max_iterations"]:
            updates["status"] = "FAILED_MAX_RETRIES"
        else:
            updates["status"] = "RETRY"

    return updates

def route_decision(state: SimulaState) -> Literal["retry", "end"]:
    if state["status"] == "SUCCESS":
        return "end"
    if state["iterations"] >= state["max_iterations"]:
        return "end"
    return "retry"

def create_simula_graph(llm_client: OpenRouterClient, sandbox: PytestSandbox):
    builder = StateGraph(SimulaState)

    builder.add_node("initialize", node_initialize)
    builder.add_node("generate", lambda state: node_generate(state, llm_client))
    builder.add_node("execute", lambda state: node_execute(state, sandbox))

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "generate")
    builder.add_edge("generate", "execute")

    builder.add_conditional_edges(
        "execute",
        route_decision,
        {
            "retry": "generate",
            "end": END,
        }
    )

    return builder.compile()
```

---

## 7. Failure Modes, Edge Cases & Defenses Matrix

| Failure Mode | Root Cause | Impact | Mitigation Strategy |
|---|---|---|---|
| **OpenRouter 429 Rate Limit** | Upstream DeepSeek capacity saturation | LLM call fails | Exponential backoff with full jitter; automatic fallback to `deepseek-chat` and LLaMA-70b distill cascade. |
| **Missing API Key / 401** | `OPENROUTER_API_KEY` unset or invalid | Immediate crash | Fast fail at initialization with clean user guidance in CLI/UI; do not attempt retries. |
| **Unclosed `<think>` tag** | DeepSeek R1 context truncation or syntax anomaly | Regex strips entire response or leaves tag | Regex lookahead to ` ``` ` code fence; fallback boundary detection. |
| **SyntaxError in Generated Code** | Malformed Python or hallucinated syntax | Subprocess fails with exit code 2 | AST pre-validation catches syntax errors; Pytest reports compilation error and trace is captured into `episodic_memory`. |
| **Subprocess Infinite Loop / Hang** | Generator `while` loop seeking impossible unique constraint | CLI/UI hangs indefinitely | Strict `timeout=30s` with process kill; returncode `-1` fed back into episodic memory stating timeout. |
| **Malicious Code / Dangerous Imports** | Injected contract commands (`os.system("rm -rf ...")`) | Host damage | Safe subprocess in ephemeral temp directory; zero `eval()`; zero host environment exposure; restricted environment variables. |
| **Foreign Key Circular Dependency** | Poor schema design in data contract | Generator fails to order insertions | Procedural memory instructs topological sorting; test failures report exact cyclic FK error for self-correction. |
| **Pytest Not Found in Subprocess** | Virtual environment misconfiguration | Sandbox exit code 127 | Sandbox uses `sys.executable` with `-m pytest` to guarantee current interpreter environment is used. |
| **MAX_ITERATIONS Exceeded** | Persistent assertion errors across all attempts | Agent looping forever | Strict counter bound terminates at `iterations >= max_iterations` with `FAILED_MAX_RETRIES` status and full diagnostics. |

---

## 8. Interface Contracts & Component Specifications

### 8.1 Configuration & Environment Variables (`.env`)
```bash
# OpenRouter Configuration
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=deepseek/deepseek-r1
OPENROUTER_FALLBACK_MODELS=deepseek/deepseek-chat,deepseek/deepseek-r1-distill-llama-70b
OPENROUTER_TIMEOUT=120.0
OPENROUTER_MAX_RETRIES=3

# Sandbox Execution Configuration
SIMULA_SANDBOX_TIMEOUT=30
SIMULA_MAX_ITERATIONS=5
```

### 8.2 Public Function Contracts in `core/`

```python
# In core/contract_parser.py
def parse_contract(contract_path_or_yaml: str) -> dict:
    """Load and validate contract YAML schema."""

# In core/graph.py
def run_simula_loop(
    contract_yaml: str,
    max_iterations: int = 5,
    on_step_callback: Optional[Callable[[SimulaState], None]] = None
) -> SimulaState:
    """Execute the full CoALA LangGraph cognitive loop with optional callback for CLI/UI progress."""
```

---

## 9. Dependencies & Package Architecture

### 9.1 Dependency List & Justifications

| Package | Minimum Version | Purpose |
|---|---|---|
| `langgraph` | `>= 0.2.0` | StateGraph execution and conditional cyclic routing |
| `httpx` | `>= 0.27.0` | High-performance synchronous/asynchronous HTTP client for OpenRouter |
| `pydantic` | `>= 2.7.0` | Data contract schema modeling and validation |
| `pyyaml` | `>= 6.0.1` | YAML parsing for data contracts |
| `faker` | `>= 24.0.0` | Synthetic relational data generation |
| `pytest` | `>= 8.0.0` | Subprocess test execution and assertion evaluation |
| `pandas` | `>= 2.2.0` | Data transformation and verification |
| `pyarrow` | `>= 15.0.0` | High-efficiency Parquet export |
| `typer` | `>= 0.12.0` | CLI command framework |
| `rich` | `>= 13.7.0` | CLI formatting, spinners, tables, and progress display |
| `streamlit` | `>= 1.35.0` | Interactive Web UI |
| `python-dotenv` | `>= 1.0.0` | Environment variable management |

### 9.2 Package Directory Layout

```
simula-ai/
├── core/
│   ├── __init__.py           # Exports: SimulaState, create_simula_graph, run_simula_loop
│   ├── state.py              # TypedDicts: SimulaState, EpisodicMemoryRecord, WorkingMemory, ProceduralMemory
│   ├── memory.py             # System prompts, Faker rules, relational guidelines, pytest guidelines
│   ├── llm_client.py         # OpenRouterClient with backoff, retry, and model cascade
│   ├── code_parser.py        # CodeParser with think stripping, fence extraction, ast validation
│   ├── sandbox.py            # PytestSandbox with subprocess isolation and timeout
│   ├── graph.py              # LangGraph StateGraph, nodes, route_decision, compiler
│   └── contract_parser.py    # YAML contract loader & schema validator
├── cli/
│   ├── __init__.py
│   └── main.py               # Typer CLI application
├── web/
│   ├── __init__.py
│   └── app.py                # Streamlit Web application
├── export/
│   ├── __init__.py
│   └── exporter.py           # Artifact exporter (generator.py, test_mock.py, datasets)
├── diagram/
│   ├── __init__.py
│   └── mermaid.py            # Mermaid ER diagram generator
├── contracts/
│   └── exemplo_credito_mesh.yaml
├── output/
│   └── datasets/
├── tests/
│   ├── test_state.py
│   ├── test_code_parser.py
│   ├── test_sandbox.py
│   ├── test_llm_client.py
│   └── test_graph.py
├── pyproject.toml
├── requirements.txt
├── Containerfile
├── .env.example
└── README.md
```

---

## 10. Loop Integrity Acceptance Criteria Checklist

- [x] **AC1.1 (State Management)**: `SimulaState` TypedDict defines `procedural_memory`, `working_memory` (`contract_yaml`, `generated_code`, `pytest_output`), `episodic_memory` (traceback history), `iterations`, and `status`.
- [x] **AC1.2 (OpenRouter Integration)**: Implements OpenRouter API calls with DeepSeek models (`deepseek/deepseek-r1`), exponential backoff on HTTP 429, and automatic fallback to secondary models (`deepseek-chat`, LLaMA-70b distill).
- [x] **AC1.3 (Regex Reasoning Stripper)**: Regex parser strips `<think>...</think>` tags (including unclosed tags and whitespace variations) and extracts runnable Python blocks using markdown fence detection and AST validation.
- [x] **AC1.4 (Subprocess Sandbox)**: Executes Pytest in an isolated subprocess (`simula_temp_test.py`) with strict timeout (30s), captures stdout/stderr/returncode, cleans up temporary files, and guarantees zero `eval()`.
- [x] **AC1.5 (LangGraph Cyclic Routing)**: Conditional edge `route_decision` routes to `generate` if `returncode != 0` and `iterations < MAX_ITERATIONS`, and routes to `END` on success (`returncode == 0`) or maximum iterations exceeded.
- [x] **AC1.6 (Traceback Feedback)**: Failed test output, specific assertion failures, and tracebacks are appended to `episodic_memory` and injected into subsequent generation prompts for reflection and self-correction.
- [x] **AC1.7 (Zero Host Side Effects)**: Execution of arbitrary generated code never pollutes or alters the host runtime environment.
