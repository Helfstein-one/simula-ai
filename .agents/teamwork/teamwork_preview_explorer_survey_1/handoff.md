# Handoff Report: Survey 1 — Core CoALA Cognitive Loop & State Management (R1)

## 1. Observation
1. **Requirements in `ORIGINAL_REQUEST.md` (lines 18-24 & 48-52)**:
   - R1 explicitly requires:
     * `SimulaState` (`TypedDict`) containing `procedural_memory`, `working_memory` (`contract_yaml`, `generated_code`, `pytest_output`), `episodic_memory` (history of iterative errors and tracebacks), `iterations`, and `status`.
     * `internal_action_generate`: Queries OpenRouter (`https://openrouter.ai/api/v1`) using DeepSeek models with HTTP 429 fallback/backoff and regex parsing stripping `<think>...</think>` tags to extract clean Python code.
     * `external_action_execute`: Pytest execution in a safe temporary subprocess sandbox (`simula_temp_test.py`) with strict timeouts, capturing stdout/stderr and return codes, with zero `eval()`.
     * `route_decision`: Loops on failure while `iterations < MAX_ITERATIONS`, terminates on success (`returncode == 0`) or max retries.
   - Loop Integrity Acceptance Criteria (lines 48-52):
     * Pytest subprocess runs in isolation with strict timeout and never uses `eval()`.
     * Parsing correctly strips `<think>` tags from DeepSeek R1 outputs and extracts runnable Python blocks.
     * Feedback loop injects traceback errors into `episodic_memory` and feeds them back to the LLM on test failures.
2. **Environment & Tooling Verification**:
   - Python versions available: `/opt/homebrew/bin/python3.12` (Python 3.12.13) and `/opt/homebrew/bin/python3.14` (Python 3.14.4).
   - Package manager: `/opt/homebrew/bin/uv` (uv 0.12.23) and `/opt/homebrew/bin/poetry`.
   - Pytest executable: `/opt/homebrew/bin/pytest` (pytest 9.1.1).
3. **Regex & AST Validation Observation**:
   - Executed prototype test for `<think>` tag stripping with unclosed tags: lookahead regex `re.sub(r"<think(?:\s+[^>]*)?>.*?(?=```)", "", text, flags=re.DOTALL | re.IGNORECASE)` cleanly isolates code blocks.
   - `ast.parse` validates extracted Python syntax prior to sandbox disk write.
4. **Peer Coordination**:
   - Explorer 2 is surveying CLI, Streamlit UI, exports, and contract YAML.
   - Explorer 3 is surveying Mermaid ER diagrams, Podman Containerfile, and packaging.

---

## 2. Logic Chain
1. **From R1 CoALA Specifications to `SimulaState`**:
   - Because CoALA requires procedural rules, working artifacts, and episodic reflection, decomposing `SimulaState` into `procedural_memory`, `working_memory`, and `episodic_memory` fulfills the cognitive architecture requirement while allowing LangGraph to serialize and pass state between nodes without side effects.
2. **From OpenRouter Realities to HTTP 429 Fallback Cascade**:
   - DeepSeek R1 on public OpenRouter gateways has high concurrency demand and frequent rate-limiting (HTTP 429). A single retry policy is insufficient; an exponential backoff with full jitter coupled with a model fallback cascade (`deepseek/deepseek-r1` -> `deepseek/deepseek-chat` -> `deepseek/deepseek-r1-distill-llama-70b`) guarantees operational resilience.
3. **From Reasoning Model Output to Regex Parsing**:
   - DeepSeek R1 emits chain-of-thought inside `<think>...</think>`. If unstripped, python interpreters raise syntax errors. If greedily stripped, unclosed tags can wipe out code blocks. The tested dual-mode regex (closed tags + unclosed lookahead to code fences) combined with `ast.parse` guarantees clean code extraction.
4. **From Sandbox Security to Subprocess Execution**:
   - Arbitrary LLM-generated Python code cannot be safely evaluated with `eval()` or `exec()` in the host process. Running `sys.executable -m pytest simula_temp_test.py` inside an ephemeral `tempfile.TemporaryDirectory` with `timeout=30s` provides isolation, captures all exit codes/tracebacks, and cleans up completely in `finally:`.
5. **From Cyclic Reflection to LangGraph StateGraph Routing**:
   - A LangGraph `StateGraph` with nodes `initialize`, `generate`, and `execute` connected to a conditional edge `route_decision` ensures deterministic termination: return code 0 transitions to `END` (`SUCCESS`), `iterations >= MAX_ITERATIONS` transitions to `END` (`FAILED_MAX_RETRIES`), and intermediate failures append tracebacks to `episodic_memory` and route back to `generate`.

---

## 3. Caveats
- OpenRouter API requires a valid `OPENROUTER_API_KEY`. In environments without an active API key or internet access, an offline mock client returning synthetic code must be provided for unit testing and CI test harnesses.
- Pytest in the subprocess sandbox requires runtime dependencies (`faker`, `pandas`, `pyarrow`, `pytest`) to be installed in the executing Python environment. The virtual environment setup must ensure these packages are in the active interpreter's `sys.path`.
- DeepSeek reasoning tags are typically lowercase `<think>`, but case-insensitive regex flags (`re.IGNORECASE`) must be used to handle casing variations.

---

## 4. Conclusion & Feature Specification Checklist

The technical architecture and specification for the Simula-AI Core CoALA Cognitive Loop (R1) is complete, verified, and documented in detail in `analysis.md`.

### Feature & Acceptance Checklist
- [x] **SimulaState Schema**:
  - [x] `procedural_memory`: Topological sorting guidelines, Faker rules, Pytest assertion rules.
  - [x] `working_memory`: Ingested `contract_yaml`, `contract_dict`, `generated_code`, `pytest_output`, `pytest_exit_code`.
  - [x] `episodic_memory`: History of iterations, exit codes, tracebacks, failed assertions, and timestamps.
  - [x] `iterations` counter, `max_iterations` limit, and `status` enum (`INIT`, `GENERATING`, `EXECUTING`, `RETRY`, `SUCCESS`, `FAILED_MAX_RETRIES`, `ERROR`).
- [x] **Internal Action (`internal_action_generate`)**:
  - [x] OpenRouter client targeting `https://openrouter.ai/api/v1/chat/completions`.
  - [x] Model cascade: `deepseek/deepseek-r1` -> `deepseek/deepseek-chat` -> `deepseek/deepseek-r1-distill-llama-70b`.
  - [x] Exponential backoff with full jitter and `Retry-After` header adherence for HTTP 429.
  - [x] Dynamic prompt assembly injecting prior iteration tracebacks from `episodic_memory`.
- [x] **Code Extraction & Regex Parser**:
  - [x] Regex stripping `<think>...</think>` (including unclosed tag lookahead).
  - [x] Markdown fence extraction (` ```python ... ``` `) selecting primary module code.
  - [x] AST validation (`ast.parse`) checking syntax integrity before sandbox execution.
- [x] **External Action Subprocess Sandbox (`external_action_execute`)**:
  - [x] Ephemeral isolated temporary directory per execution (`tempfile.TemporaryDirectory`).
  - [x] Zero `eval()` / zero `exec()` in host process.
  - [x] Subprocess execution of `pytest simula_temp_test.py` with strict configurable timeout (30s).
  - [x] Automatic process killing on timeout (`subprocess.TimeoutExpired`).
  - [x] Structured stdout, stderr, and return code capture.
- [x] **LangGraph StateGraph & Routing (`route_decision`)**:
  - [x] Nodes: `node_initialize`, `node_generate`, `node_execute`.
  - [x] Conditional edge routing: `exit_code == 0` -> SUCCESS (`END`), `iterations >= MAX_ITERATIONS` -> FAILED_MAX_RETRIES (`END`), test failure -> RETRY (`node_generate`).
  - [x] Self-correcting feedback loop appending failure summaries to `episodic_memory`.
- [x] **Package & Dependency Blueprint**:
  - [x] Clean modular structure in `core/` (`state.py`, `memory.py`, `llm_client.py`, `code_parser.py`, `sandbox.py`, `graph.py`, `contract_parser.py`).
  - [x] Complete dependency specifications (`langgraph`, `httpx`, `pydantic`, `pyyaml`, `faker`, `pytest`, `pandas`, `pyarrow`, `typer`, `rich`, `streamlit`, `python-dotenv`).

---

## 5. Verification Method

To independently verify the survey observations, code parsing regex, and sandbox mechanics:
1. **Inspect Analysis and Specification**:
   - Read `/Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_survey_1/analysis.md`.
2. **Verify Regex Parser with `<think>` Stripping & AST**:
   ```bash
   /opt/homebrew/bin/python3.12 -c '
   import re, ast
   text = "<think>\nReasoning steps...\n</think>\n```python\nimport faker\ndef test_ok(): assert True\n```"
   cleaned = re.sub(r"<think(?:\s+[^>]*)?>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
   code = re.findall(r"```(?:python|py)?\s*\n(.*?)```", cleaned, flags=re.DOTALL)[0]
   ast.parse(code)
   print("Regex and AST verification SUCCESS!")
   '
   ```
3. **Verify Isolated Pytest Subprocess Execution**:
   ```bash
   /opt/homebrew/bin/python3.12 -c '
   import subprocess, tempfile, sys
   from pathlib import Path
   with tempfile.TemporaryDirectory() as tmpdir:
       f = Path(tmpdir) / "simula_temp_test.py"
       f.write_text("def test_sample(): assert 1 + 1 == 2")
       res = subprocess.run([sys.executable, "-m", "pytest", str(f)], capture_output=True, text=True)
       print("Subprocess pytest exit code:", res.returncode)
   '
   ```
4. **Invalidation Conditions**:
   - The specification is invalidated if OpenRouter discontinues DeepSeek model endpoints or changes its standard OpenAI-compatible `/chat/completions` API structure without fallback.
   - The specification is invalidated if LangGraph deprecates `StateGraph` conditional edges.
