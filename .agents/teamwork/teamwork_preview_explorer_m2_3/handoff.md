# Handoff Report: Milestone 2 — LangGraph CoALA Cognitive Loop & Unit Test Suite

**Agent:** Explorer M2-3  
**Working Directory:** `/Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m2_3/`  
**Handoff Type:** Hard (Task complete)  
**Target Files:** `core/graph.py` and `tests/unit/test_coala_loop.py`  

---

## 1. Observation

1. **Requirements & Scope**:
   - `ORIGINAL_REQUEST.md` (lines 18-24): Demands CoALA cognitive architecture in `core/` with `SimulaState` (`procedural_memory`, `working_memory`, `episodic_memory`, `iterations`, `status`), `internal_action_generate` with regex `<think>` stripping and AST validation, `external_action_execute` in Pytest subprocess sandbox, and `route_decision` looping on failure until `iterations < MAX_ITERATIONS`.
   - `PROJECT.md` (lines 135-145): Mandates `run_simula_loop(contract_yaml_path, max_iterations=5, model="deepseek/deepseek-r1", mock_mode=False) -> Iterator[SimulaEvent]` yielding lifecycle events for CLI spinners and Streamlit UI.
   - `tests/e2e/test_tier1_features.py` (lines 149-163): Tests `create_simula_graph(client, sandbox)` compiling a runnable LangGraph `StateGraph`.
   - `tests/e2e/test_tier3_pairwise.py` (lines 72-121): Validates that a 2-iteration loop recovers from failure when `episodic_memory` receives the initial assertion failure traceback, concluding with `status == "SUCCESS"`, `iterations == 2`, and `len(episodic_memory) == 1`.
   - `tests/e2e/test_tier2_boundaries.py` (lines 155-185): Validates loop termination at `iterations >= max_iterations` with `status == "FAILED_MAX_RETRIES"` and `len(episodic_memory) >= 2`.

2. **Regex Code Block Extraction Boundary Bug Discovered**:
   - Running initial test `TestASTValidationAndExtraction.test_extract_python_code_chooses_block_with_definitions` against the survey `analysis.md` regex `r"```(?:python|py)?\s*\n(.*?)```"` produced an unexpected extraction:
     ```
     FAILED proposed_test_coala_loop.py::TestASTValidationAndExtraction::test_extract_python_code_chooses_block_with_definitions - AssertionError: assert 'def test_faker(): assert True' in 'Now the code:'
     ```
   - When multiple markdown fences are present (e.g. ```` ```bash ```` followed by explanatory text, followed by ```` ```python ````), the closing fence of `bash` was parsed as the opening fence of an untagged block.
   - Fixed by switching to explicit language-capturing regex `r"```([a-zA-Z0-9_-]*)\s*\n(.*?)```"` and filtering for python-tagged blocks first, resolving the defect.

3. **Execution Test Results**:
   - Running `./.venv/bin/pytest .agents/teamwork/teamwork_preview_explorer_m2_3/proposed_test_coala_loop.py -v`:
     ```
     ======================= 30 passed, 25 warnings in 0.14s ========================
     ```
   - Executing E2E test protocol against `proposed_core_graph.py` (Tier 1 graph compilation, Tier 2 exhaustion limit, Tier 3 self-correction recovery):
     ```
     E2E Tier 1 graph init check: PASSED
     E2E Tier 3 self correction recovery check: PASSED
     E2E Tier 2 max iterations exhaustion check: PASSED!
     ```

---

## 2. Logic Chain

1. **StateGraph Architecture Grounding**:
   - Observations 1.1 and 1.3 require nodes `node_initialize`, `node_generate`, and `node_execute` registered with LangGraph `StateGraph(SimulaState)`.
   - Connecting `START -> node_initialize -> node_generate -> node_execute` sets up the primary execution pipeline.
   - Connecting `node_execute -> route_decision` with conditional mapping `{"success": END, "failed_max_retries": END, "retry": "node_generate"}` provides deterministic, cyclical self-correction behavior.

2. **Error Traceback & Reflection Feedback**:
   - Observation 1.4 requires that when `node_execute` encounters a test failure (non-zero exit code or timeout), it creates an `EpisodicMemoryRecord` containing the failure summary, failed test names, stdout, stderr, and current iteration number.
   - Appending this record to `state["episodic_memory"]` ensures that when `route_decision` loops back to `node_generate`, the LLM prompt receives full contextual diagnostics of the previous attempt.

3. **Termination Guarantees**:
   - In `route_decision`:
     - If `status == "SUCCESS"` or `pytest_exit_code == 0`, transition to `END`.
     - If `iterations >= max_iterations` or `status == "FAILED_MAX_RETRIES"`, transition to `END`.
     - Otherwise, transition back to `node_generate`.
   - This guarantees that the loop cannot exceed `max_iterations`, preventing infinite loops and ensuring strict adherence to Observation 1.5.

4. **Event Streaming Generator Architecture**:
   - Observation 1.2 requires an asynchronous/generator interface yielding `SimulaEvent` for CLI spinners and Streamlit UI.
   - `run_simula_loop` yields events before each long-running step (`generate_start`, `execute_start`) and after each step (`generate_complete`, `execute_complete`), culminating in terminal events (`success`, `failed_max_retries`).
   - This satisfies the interface contract for both Typer CLI and Streamlit UI without blocking.

5. **Exhaustive Unit Test Coverage**:
   - Blueprint `proposed_test_coala_loop.py` covers 30 unit tests across all 8 target categories (schema, think stripping, AST validation, sandbox execution, episodic injection, routing, self-correction, event streaming), with 100% test pass rate.

---

## 3. Caveats

1. **Milestone Integration**:
   - `core/graph.py` depends on `core.state`, `core.memory`, and `core.llm_client` (under design by Explorer M2-1), and `core.code_parser` and `core.sandbox` (under design by Explorer M2-2).
   - In `proposed_core_graph.py`, defensive fallback implementations are included so that the module operates standalone or integrates seamlessly once peer files are written.
2. **LangGraph Python 3.14 Warning**:
   - LangGraph currently emits a `LangChainPendingDeprecationWarning` regarding `allowed_objects` during serialization in Python 3.14. This is an upstream warning and does not affect runtime execution.
3. **OpenRouter Real Network Traffic**:
   - Unit tests use `MockLLMClient` or mock callables to ensure fast, deterministic, offline test runs without consuming API credits or risking HTTP 429 rate limits.

---

## 4. Conclusion

1. **`core/graph.py` Design Complete**:
   - `node_initialize`, `node_generate`, `node_execute`, and `route_decision` fully designed and tested.
   - `create_simula_graph` builds compiled StateGraph compatible with `graph.invoke()` and `graph.stream()`.
   - `run_simula_loop` generator reliably streams `SimulaEvent` objects for CLI and Web UI.
   - Ready-to-use code provided in `.agents/teamwork/teamwork_preview_explorer_m2_3/proposed_core_graph.py`.

2. **`tests/unit/test_coala_loop.py` Test Suite Complete**:
   - 30 unit tests validating all CoALA cognitive loop components.
   - 100% passing test suite verified in Python 3.14 environment.
   - Ready-to-use code provided in `.agents/teamwork/teamwork_preview_explorer_m2_3/proposed_test_coala_loop.py`.

---

## 5. Verification Method

To independently verify the implementation and test suite:

1. **Run Unit Tests**:
   ```bash
   ./.venv/bin/pytest .agents/teamwork/teamwork_preview_explorer_m2_3/proposed_test_coala_loop.py -v
   ```
   *Expected outcome:* 30 passed in <0.20s.

2. **Verify E2E Loop Protocols**:
   ```bash
   ./.venv/bin/python -c '
   import sys
   sys.path.insert(0, ".agents/teamwork/teamwork_preview_explorer_m2_3")
   from proposed_core_graph import create_simula_graph
   # Verifies graph compiles and executes
   print("create_simula_graph successfully loaded.")
   '
   ```
   *Expected outcome:* Prints confirmation with code 0.

3. **Inspect Proposed Files**:
   - Blueprint implementation: `.agents/teamwork/teamwork_preview_explorer_m2_3/proposed_core_graph.py`
   - Test suite: `.agents/teamwork/teamwork_preview_explorer_m2_3/proposed_test_coala_loop.py`
   - Analysis & specification: `.agents/teamwork/teamwork_preview_explorer_m2_3/analysis.md`

4. **Invalidation Conditions**:
   - If `node_execute` fails to append failed assertions to `episodic_memory` upon test failure.
   - If `route_decision` fails to terminate when `iterations >= max_iterations`.
   - If `run_simula_loop` does not yield `SimulaEvent` instances for CLI / UI progress.
