# Forensic Audit Report — Milestone 2: CoALA Cognitive Loop & Sandbox

**Work Product**: Milestone 2 Modules (`core/state.py`, `core/memory.py`, `core/llm_client.py`, `core/code_parser.py`, `core/sandbox.py`, `core/graph.py`, `core/__init__.py`, `tests/unit/test_coala_loop.py`)  
**Profile**: General Project  
**Integrity Mode**: Development (from `ORIGINAL_REQUEST.md` line 14)  
**Verdict**: **CLEAN**

---

## 1. Observation

### A. Static Code Inspection & Prohibited Pattern Scans
- **Eval/Exec Prohibited Pattern**:
  Ran ripgrep for `\b(eval|exec)\s*\(` across `/Users/mauriciohelfstein/dev/simula-ai/core`.
  - Output: Single match at `core/memory.py:55`: `"- Never use `eval()` or `exec()`."` (inside docstring/prompt instructions). Zero calls to `eval()` or `exec()` exist in any production module.
- **Pre-populated Artifact Scan**:
  Ran `find . -maxdepth 3 -name '*.log' -o -name '*result*' -o -name '*output*'`.
  - Output: Empty. No pre-populated logs, mock result files, or cached attestations.
- **Facade and Dummy Constants**:
  Examined `core/code_parser.py`, `core/sandbox.py`, `core/graph.py`, `core/memory.py`, and `core/llm_client.py`.
  - All methods contain genuine procedural and computational logic. Functions compute returns dynamically based on input arguments and state transitions.

### B. Pytest Sandbox Subprocess Isolation
- Inspected `core/sandbox.py` lines 61–104:
  - Generates an ephemeral `tempfile.TemporaryDirectory(prefix="simula_sandbox_")`.
  - Writes candidate code to `simula_temp_test.py`.
  - Invokes `subprocess.run` with `[sys.executable, "-m", "pytest", "simula_temp_test.py", "-v", "--tb=short", "-p", "no:cacheprovider"]`.
  - Enforces `timeout=self.timeout_seconds` via `subprocess.TimeoutExpired`.
  - Captures `res.stdout`, `res.stderr`, `res.returncode`.
  - `_parse_failures` extracts exact failing test function names and failure traceback slices using regex.
- Empirically executed `PytestSandbox(timeout_seconds=5)` against:
  - Valid test: returned `exit_code: 0`, `is_success: True`, `failed_tests: []`.
  - Failing test (`assert 5 - 2 == 4`): returned `exit_code: 1`, `is_success: False`, `failed_tests: ['test_sub']`.
  - Hanging test (`time.sleep(10)`): returned `exit_code: -1`, `timed_out: True`, elapsed `5.01s`.

### C. Regex Stripping & AST Validation
- Inspected `core/code_parser.py`:
  - `strip_think_tags`: Applies regex `THINK_TAG_REGEX`, `UNCLOSED_THINK_REGEX`, and `UNCLOSED_THINK_NO_FENCE_REGEX`. Tested against closed `<think>...</think>`, attribute-bearing `<think model="r1">`, and unclosed `<think>...` followed by code blocks.
  - `extract_python_code`: Extracts markdown code blocks, prioritizes python syntax, validates syntax via `ast.parse` inside scoring heuristic.
  - `validate_syntax`: Direct `ast.parse` call returning boolean and syntax error diagnostic without code execution.

### D. LangGraph StateGraph Architecture & Event Streaming
- Inspected `core/graph.py`:
  - `create_simula_graph`: Genuinely constructs `StateGraph(SimulaState)` with nodes `node_initialize`, `node_generate`, and `node_execute`. Connects `START` to `node_initialize`, `node_initialize` to `node_generate`, `node_generate` to `node_execute`.
  - Adds conditional edges via `route_decision`:
    - `success -> END`
    - `failed_max_retries -> END`
    - `retry -> node_generate`
  - Empirically executed `graph.invoke(initial_state)` using `MockLLMClient(fail_first_iteration=True)` and real `PytestSandbox`:
    - Iteration 1 failed Pytest validation (`assert 1 == 2`).
    - Captured traceback in `episodic_memory[0]`.
    - Iteration 2 received episodic memory feedback, corrected code (`assert 1 == 1`).
    - Sandbox returned exit code 0; `route_decision` transitioned to `SUCCESS` at iteration 2.
  - Inspected `run_simula_loop`: Event generator yielding 7 distinct lifecycle events (`init_start`, `init_complete`, `generate_start`, `generate_complete`, `execute_start`, `execute_complete`, `success`/`retry`/`failed_max_retries`). Tested against `contracts/exemplo_credito_mesh.yaml`.

### E. OpenRouter LLM Client Resilience
- Inspected `core/llm_client.py`:
  - `OpenRouterClient`: Connects to `https://openrouter.ai/api/v1/chat/completions`.
  - Implements exponential backoff with full jitter on HTTP 429 and transient 5xx errors via `_calculate_jitter_delay`.
  - Respects `Retry-After` header.
  - Fallback cascade across models: `deepseek/deepseek-r1` -> `deepseek/deepseek-chat` -> `deepseek/deepseek-r1-distill-llama-70b`.
  - Empirically simulated HTTP 401 auth error and HTTP 429 rate limit cascade with mock HTTP responses; cascade correctly stepped to next fallback model.

### F. Test Validity & Assertion Quality
- Inspected all 30 tests in `tests/unit/test_coala_loop.py`:
  - Zero tautological assertions (`assert True` or constant comparisons without verifying output).
  - All assertions check actual schema annotations, AST parse outputs, regex strip outputs, state updates, exit codes, episodic memory accumulation, and graph outcomes.
- Ran test suite using `/Users/mauriciohelfstein/dev/simula-ai/.venv/bin/pytest`:
  - `tests/unit/test_coala_loop.py`: 30 passed in 1.35s.
  - Entire suite (`tests/`): 77 passed, 20 skipped (requiring network API keys).

---

## 2. Logic Chain

1. **Rule Compliance**: `ORIGINAL_REQUEST.md` specifies `Integrity mode: development`. Under development mode, external libraries (LangGraph, Pytest, Faker, httpx) and mock test doubles are permitted; hardcoded test outputs, dummy facades, fabricated logs, and `eval()`/`exec()` are strictly prohibited.
2. **Subprocess Isolation**: Inspection and empirical execution confirm that `PytestSandbox` runs `sys.executable -m pytest` in an isolated temp directory with real subprocess timeouts and zero `eval()`.
3. **Cognitive Loop Integrity**: Empirical test runs proved that `create_simula_graph` constructs and compiles a genuine LangGraph `StateGraph`. On simulated test failure, error traces are parsed and stored in `episodic_memory`, which is passed to the next iteration for self-correction.
4. **Parser Authenticity**: `CodeParser` uses genuine regular expressions for `<think>` tag stripping and `ast.parse` for syntax verification.
5. **Test Authenticity**: All unit tests in `tests/unit/test_coala_loop.py` execute genuine assertions verifying structure, logic, and state behavior without shortcuts.
6. **Conclusion Follows Directly**: No prohibited patterns exist, all core requirements are authentically satisfied, and all tests pass with genuine assertions.

---

## 3. Caveats

- Live HTTP completions against OpenRouter API require a funded `OPENROUTER_API_KEY`; testing of the network layer was verified via mock injection and fallback unit tests, consistent with offline development integrity standards.

---

## 4. Conclusion

**Verdict: CLEAN**

Milestone 2 fully conforms to CoALA architectural specifications, achieves complete subprocess isolation without `eval()`/`exec()`, compiles and executes genuine LangGraph StateGraphs, provides robust AST and regex parsing, and includes authentic, comprehensive unit tests.

---

## 5. Verification Method

To independently reproduce all forensic audit checks:

```bash
cd /Users/mauriciohelfstein/dev/simula-ai

# 1. Run unit test suite for Milestone 2
.venv/bin/pytest -v tests/unit/test_coala_loop.py

# 2. Verify zero eval/exec in core modules
grep -rnE "\b(eval|exec)\s*\(" core/

# 3. Empirical verification of StateGraph + PytestSandbox subprocess execution
.venv/bin/python -c '
from core.graph import create_simula_graph
from core.sandbox import PytestSandbox
from core.llm_client import MockLLMClient
from core.state import create_initial_state

mock_client = MockLLMClient(fail_first_iteration=True)
sandbox = PytestSandbox(timeout_seconds=10)
graph = create_simula_graph(mock_client, sandbox)

state = create_initial_state(contract_yaml="mesh_name: credit\ntables: []", max_iterations=3)
result = graph.invoke(state)

assert result["status"] == "SUCCESS"
assert result["iterations"] == 2
assert len(result["episodic_memory"]) == 1
print("Empirical Verification Succeeded: StateGraph compiled, sandbox isolated, CoALA loop verified.")
'
```
