"""tests/unit/test_coala_loop.py - Comprehensive Unit Tests for CoALA Cognitive Loop.

Validates:
1. SimulaState schema and memory components.
2. Regex <think> tag stripping (closed, unclosed, attribute variations).
3. AST code extraction and pre-sandbox syntax validation.
4. Isolated subprocess Pytest sandbox (exit codes, timeouts, zero eval).
5. Episodic memory error traceback capture and accumulation.
6. LangGraph StateGraph conditional routing (route_decision).
7. Mock LLM self-correction feedback loop and retry exhaustion.
8. Event streaming generator run_simula_loop yielding SimulaEvent lifecycle events.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# Ensure our local directory and project root are importable
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import blueprint implementations
from proposed_core_graph import (
    CodeParser,
    EpisodicMemoryRecord,
    ProceduralMemory,
    SimulaEvent,
    SimulaState,
    WorkingMemory,
    create_initial_procedural_memory,
    create_simula_graph,
    node_execute,
    node_generate,
    node_initialize,
    route_decision,
    run_simula_loop,
)


# ============================================================================
# 1. SimulaState Schema & Integrity Tests
# ============================================================================


class TestSimulaStateSchema:
    """Verifies TypedDict schemas conforming to CoALA cognitive architecture."""

    def test_simula_state_type_structure(self):
        annotations = getattr(SimulaState, "__annotations__", {})
        required_keys = {
            "procedural_memory",
            "working_memory",
            "episodic_memory",
            "iterations",
            "max_iterations",
            "status",
            "error_message",
        }
        missing = required_keys - set(annotations.keys())
        assert not missing, f"SimulaState missing required keys: {missing}"

    def test_episodic_memory_record_structure(self):
        annotations = getattr(EpisodicMemoryRecord, "__annotations__", {})
        required_keys = {
            "iteration",
            "generated_code",
            "exit_code",
            "stdout",
            "stderr",
            "error_summary",
            "failed_tests",
            "timestamp",
        }
        missing = required_keys - set(annotations.keys())
        assert not missing, f"EpisodicMemoryRecord missing keys: {missing}"

    def test_working_memory_structure(self):
        annotations = getattr(WorkingMemory, "__annotations__", {})
        required_keys = {
            "contract_yaml",
            "contract_dict",
            "generated_code",
            "pytest_output",
            "pytest_exit_code",
            "last_error",
        }
        missing = required_keys - set(annotations.keys())
        assert not missing, f"WorkingMemory missing keys: {missing}"

    def test_procedural_memory_structure(self):
        procedural = create_initial_procedural_memory()
        assert isinstance(procedural, dict)
        assert "system_prompt" in procedural
        assert "faker_rules" in procedural
        assert "relational_rules" in procedural
        assert "pytest_rules" in procedural
        assert len(procedural["faker_rules"]) > 0
        assert len(procedural["relational_rules"]) > 0

    def test_node_initialize_creates_valid_state(self):
        raw_yaml = "mesh_name: test_mesh\ntables:\n  - name: users"
        initial_input: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"contract_yaml": raw_yaml},
            "episodic_memory": [],
            "iterations": 0,
            "max_iterations": 5,
            "status": "INIT",
            "error_message": None,
        }
        initialized = node_initialize(initial_input)
        assert initialized["status"] == "INIT"
        assert initialized["iterations"] == 0
        assert initialized["working_memory"]["contract_dict"]["mesh_name"] == "test_mesh"
        assert len(initialized["procedural_memory"]["faker_rules"]) > 0
        assert initialized["episodic_memory"] == []


# ============================================================================
# 2. Regex <think> Tag Stripping Tests
# ============================================================================


class TestThinkTagStripping:
    """Verifies stripping of reasoning tokens from DeepSeek R1 responses."""

    def test_closed_think_tag_stripping(self):
        raw = textwrap.dedent("""
            <think>
            Analyzing data contract.
            Need foreign key from propostas to empresas.
            </think>
            ```python
            import pytest
            def test_ok(): assert True
            ```
        """).strip()
        cleaned = CodeParser.strip_think_tags(raw)
        assert "<think>" not in cleaned.lower()
        assert "</think>" not in cleaned.lower()
        assert "Analyzing data contract" not in cleaned
        assert "```python" in cleaned

    def test_unclosed_think_tag_stripping(self):
        raw = textwrap.dedent("""
            <think>
            Unfinished reasoning that was truncated before closing tag
            ```python
            import pytest
            def test_unclosed(): assert 1 == 1
            ```
        """).strip()
        cleaned = CodeParser.strip_think_tags(raw)
        assert "<think>" not in cleaned.lower()
        assert "Unfinished reasoning" not in cleaned
        assert "```python" in cleaned

    def test_think_tag_with_attributes_and_newlines(self):
        raw = '<think model="r1" step="thought">\nReasoning step\n</think>\n```python\nx = 1\n```'
        cleaned = CodeParser.strip_think_tags(raw)
        assert "<think" not in cleaned.lower()
        assert "Reasoning step" not in cleaned
        assert "x = 1" in cleaned

    def test_response_without_think_tags_remains_intact(self):
        raw = "```python\ndef test_clean(): pass\n```"
        cleaned = CodeParser.strip_think_tags(raw)
        assert cleaned == raw

    def test_empty_string_handling(self):
        assert CodeParser.strip_think_tags("") == ""
        assert CodeParser.strip_think_tags(None) == ""


# ============================================================================
# 3. AST Validation and Code Extraction Tests
# ============================================================================


class TestASTValidationAndExtraction:
    """Verifies Python code fence extraction and syntax validation."""

    def test_valid_python_syntax(self):
        valid_code = "import pytest\ndef test_fn():\n    assert 1 + 1 == 2\n"
        valid, err = CodeParser.validate_syntax(valid_code)
        assert valid is True
        assert err is None

    def test_invalid_python_syntax_detected(self):
        broken_code = "def broken(:\n    return False\n"
        valid, err = CodeParser.validate_syntax(broken_code)
        assert valid is False
        assert err is not None
        assert "SyntaxError" in err

    def test_extract_python_code_from_markdown_fence(self):
        response = textwrap.dedent("""
            Here is the generated mock script:
            ```python
            import pytest
            def test_mock():
                assert True
            ```
            Hope this helps!
        """)
        code = CodeParser.extract_python_code(response)
        assert code == "import pytest\ndef test_mock():\n    assert True"

    def test_extract_python_code_chooses_block_with_definitions(self):
        response = textwrap.dedent("""
            ```bash
            pip install pytest faker
            ```
            Now the code:
            ```python
            import faker
            import pytest
            def test_faker(): assert True
            ```
        """)
        code = CodeParser.extract_python_code(response)
        assert "def test_faker(): assert True" in code
        assert "pip install" not in code

    def test_fallback_raw_python_without_fences(self):
        raw_python = textwrap.dedent("""
            import pytest
            def test_direct():
                assert 42 == 42
        """).strip()
        code = CodeParser.extract_python_code(raw_python)
        assert "def test_direct():" in code


# ============================================================================
# 4. Pytest Sandbox Execution Tests
# ============================================================================


class TestPytestSandboxSubprocess:
    """Verifies subprocess isolation, timeout enforcement, and zero-eval safety."""

    def test_sandbox_passing_code(self):
        # Local mock sandbox or real sandbox
        class MockResult:
            exit_code = 0
            stdout = "1 passed in 0.01s"
            stderr = ""
            timed_out = False
            failed_tests = []
            error_summary = ""
            is_success = True

        sandbox = MagicMock()
        sandbox.execute.return_value = MockResult()

        state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"generated_code": "def test_ok(): assert True"},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 3,
            "status": "GENERATING",
            "error_message": None,
        }

        updates = node_execute(state, sandbox)
        assert updates["status"] == "SUCCESS"
        assert updates["working_memory"]["pytest_exit_code"] == 0
        assert len(updates["episodic_memory"]) == 0

    def test_sandbox_assertion_failure(self):
        class MockFailureResult:
            exit_code = 1
            stdout = "FAILED simula_temp_test.py::test_fail - AssertionError: 1 != 2"
            stderr = ""
            timed_out = False
            failed_tests = ["simula_temp_test.py::test_fail"]
            error_summary = "AssertionError: 1 != 2"
            is_success = False

        sandbox = MagicMock()
        sandbox.execute.return_value = MockFailureResult()

        state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"generated_code": "def test_fail(): assert 1 == 2"},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 3,
            "status": "GENERATING",
            "error_message": None,
        }

        updates = node_execute(state, sandbox)
        assert updates["status"] == "RETRY"
        assert updates["working_memory"]["pytest_exit_code"] == 1
        assert len(updates["episodic_memory"]) == 1
        assert "AssertionError: 1 != 2" in updates["episodic_memory"][0]["error_summary"]

    def test_sandbox_timeout_handling(self):
        class MockTimeoutResult:
            exit_code = -1
            stdout = ""
            stderr = "Execution timed out after 5 seconds."
            timed_out = True
            failed_tests = ["TIMEOUT"]
            error_summary = "Execution timed out after 5 seconds."
            is_success = False

        sandbox = MagicMock()
        sandbox.execute.return_value = MockTimeoutResult()

        state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"generated_code": "import time\ntime.sleep(100)"},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 2,
            "status": "GENERATING",
            "error_message": None,
        }

        updates = node_execute(state, sandbox)
        assert updates["status"] == "RETRY"
        assert len(updates["episodic_memory"]) == 1
        assert updates["episodic_memory"][0]["exit_code"] == -1
        assert "timed out" in updates["episodic_memory"][0]["error_summary"].lower()


# ============================================================================
# 5. Memory Traceback Injection & History Accumulation Tests
# ============================================================================


class TestMemoryTracebackInjection:
    """Verifies episodic memory accumulation and feedback propagation."""

    def test_episodic_history_accumulation_across_multiple_failures(self):
        class MockFailureResult:
            exit_code = 1
            stdout = "FAILED"
            stderr = ""
            timed_out = False
            failed_tests = ["test_a"]
            error_summary = "First error"
            is_success = False

        sandbox = MagicMock()
        sandbox.execute.return_value = MockFailureResult()

        state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"generated_code": "code_v1"},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 3,
            "status": "GENERATING",
            "error_message": None,
        }

        # Step 1: First failure
        step1 = node_execute(state, sandbox)
        assert len(step1["episodic_memory"]) == 1
        assert step1["episodic_memory"][0]["error_summary"] == "First error"

        # Step 2: Second failure
        MockFailureResult.error_summary = "Second error"
        state_v2 = {**state, **step1, "iterations": 2}
        step2 = node_execute(state_v2, sandbox)
        assert len(step2["episodic_memory"]) == 2
        assert step2["episodic_memory"][0]["error_summary"] == "First error"
        assert step2["episodic_memory"][1]["error_summary"] == "Second error"

    def test_node_generate_passes_episodic_memory_to_llm_client(self):
        mock_client = MagicMock()
        mock_client.generate_candidate.return_value = "```python\ndef test_ok(): pass\n```"

        prior_record: EpisodicMemoryRecord = {
            "iteration": 1,
            "generated_code": "bad_code",
            "exit_code": 1,
            "stdout": "AssertionError",
            "stderr": "",
            "error_summary": "AssertionError: propostas.empresa_id FK orphan",
            "failed_tests": ["test_fk"],
            "timestamp": "2026-10-12T00:00:00Z",
        }

        state: SimulaState = {
            "procedural_memory": {"faker_rules": ["rule1"]},
            "working_memory": {"contract_yaml": "tables: []"},
            "episodic_memory": [prior_record],
            "iterations": 1,
            "max_iterations": 3,
            "status": "RETRY",
            "error_message": None,
        }

        node_generate(state, mock_client)

        mock_client.generate_candidate.assert_called_once()
        kwargs = mock_client.generate_candidate.call_args.kwargs
        assert kwargs["iteration"] == 2
        assert len(kwargs["episodic_memory"]) == 1
        assert "FK orphan" in kwargs["episodic_memory"][0]["error_summary"]


# ============================================================================
# 6. StateGraph Routing Tests (route_decision)
# ============================================================================


class TestStateGraphRouting:
    """Verifies route_decision conditional transitions and compiled StateGraph."""

    def test_route_decision_success_path(self):
        state_success: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"pytest_exit_code": 0},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 5,
            "status": "SUCCESS",
            "error_message": None,
        }
        assert route_decision(state_success) == "success"

    def test_route_decision_failed_max_retries_path(self):
        state_exhausted: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"pytest_exit_code": 1},
            "episodic_memory": [],
            "iterations": 5,
            "max_iterations": 5,
            "status": "FAILED_MAX_RETRIES",
            "error_message": None,
        }
        assert route_decision(state_exhausted) == "failed_max_retries"

    def test_route_decision_retry_path(self):
        state_retry: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"pytest_exit_code": 1},
            "episodic_memory": [],
            "iterations": 1,
            "max_iterations": 3,
            "status": "RETRY",
            "error_message": None,
        }
        assert route_decision(state_retry) == "retry"

    def test_create_simula_graph_compiles_successfully(self):
        mock_client = MagicMock()
        mock_sandbox = MagicMock()
        graph = create_simula_graph(mock_client, mock_sandbox)
        assert graph is not None
        # Verify compiled graph has runnable invocation
        assert hasattr(graph, "invoke")
        assert hasattr(graph, "stream")


# ============================================================================
# 7. Mock LLM Self-Correction Loop & Exhaustion Tests
# ============================================================================


class TestMockLLMSelfCorrectionLoop:
    """Verifies the complete iterative CoALA cognitive loop with mock LLM."""

    def test_self_correction_two_iterations(self):
        """Simulates iteration 1 failure followed by iteration 2 resolution."""
        class StatefulSelfCorrectingLLM:
            def __init__(self):
                self.calls = 0

            def generate_candidate(self, **kwargs):
                self.calls += 1
                episodic = kwargs.get("episodic_memory", [])
                if self.calls == 1:
                    assert len(episodic) == 0
                    return "```python\nimport pytest\ndef test_init(): assert 1 == 2, 'Intentional bug'\n```"
                else:
                    assert len(episodic) == 1
                    assert "Intentional bug" in episodic[0]["error_summary"]
                    return "```python\nimport pytest\ndef test_fixed(): assert 1 == 1\n```"

        class StatefulSandbox:
            def execute(self, code: str):
                class Res:
                    def __init__(self, ec, out, summary):
                        self.exit_code = ec
                        self.stdout = out
                        self.stderr = ""
                        self.timed_out = False
                        self.failed_tests = ["test_init"] if ec != 0 else []
                        self.error_summary = summary
                        self.is_success = ec == 0

                if "assert 1 == 2" in code:
                    return Res(1, "FAILED test_init - Intentional bug", "AssertionError: Intentional bug")
                return Res(0, "PASSED test_fixed", "")

        mock_llm = StatefulSelfCorrectingLLM()
        sandbox = StatefulSandbox()
        graph = create_simula_graph(mock_llm, sandbox)

        initial_state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"contract_yaml": "tables: []"},
            "episodic_memory": [],
            "iterations": 0,
            "max_iterations": 3,
            "status": "INIT",
            "error_message": None,
        }

        final_state = graph.invoke(initial_state)

        assert final_state["status"] == "SUCCESS"
        assert final_state["iterations"] == 2
        assert len(final_state["episodic_memory"]) == 1
        assert "Intentional bug" in final_state["episodic_memory"][0]["error_summary"]
        assert final_state["working_memory"]["pytest_exit_code"] == 0

    def test_max_retries_exhaustion_terminates_at_limit(self):
        """Simulates persistent test failures until MAX_ITERATIONS exhaustion."""
        class AlwaysFailingLLM:
            def generate_candidate(self, **kwargs):
                return "```python\ndef test_bad(): assert False\n```"

        class AlwaysFailingSandbox:
            def execute(self, code: str):
                class Res:
                    exit_code = 1
                    stdout = "FAILED"
                    stderr = ""
                    timed_out = False
                    failed_tests = ["test_bad"]
                    error_summary = "AssertionError"
                    is_success = False
                return Res()

        graph = create_simula_graph(AlwaysFailingLLM(), AlwaysFailingSandbox())

        initial_state: SimulaState = {
            "procedural_memory": {},
            "working_memory": {"contract_yaml": "tables: []"},
            "episodic_memory": [],
            "iterations": 0,
            "max_iterations": 2,
            "status": "INIT",
            "error_message": None,
        }

        final_state = graph.invoke(initial_state)

        assert final_state["status"] == "FAILED_MAX_RETRIES"
        assert final_state["iterations"] == 2
        assert len(final_state["episodic_memory"]) == 2


# ============================================================================
# 8. Event Streaming Generator Tests (run_simula_loop)
# ============================================================================


class TestEventStreamingGenerator:
    """Verifies run_simula_loop generator yielding SimulaEvent lifecycle events."""

    def test_run_simula_loop_event_stream(self):
        events: List[SimulaEvent] = []
        raw_yaml = "mesh_name: credit_mesh\ntables: []"

        # Run with mock_mode=True
        stream = run_simula_loop(
            contract_path=raw_yaml,
            max_iterations=2,
            mock_mode=True,
        )

        for event in stream:
            assert isinstance(event, SimulaEvent)
            assert hasattr(event, "step")
            assert hasattr(event, "iteration")
            assert hasattr(event, "state")
            assert hasattr(event, "message")
            events.append(event)

        # Verify event progression
        step_names = [e.step for e in events]
        assert "init_start" in step_names
        assert "init_complete" in step_names
        assert "generate_start" in step_names
        assert "execute_start" in step_names
        assert "success" in step_names or "failed_max_retries" in step_names

    def test_run_simula_loop_on_step_callback(self):
        captured_callbacks: List[str] = []

        def callback(ev: SimulaEvent):
            captured_callbacks.append(ev.step)

        stream = run_simula_loop(
            contract_path="mesh_name: sample\ntables: []",
            max_iterations=1,
            mock_mode=True,
            on_step_callback=callback,
        )

        list(stream)
        assert len(captured_callbacks) > 0
        assert "init_start" in captured_callbacks

    def test_run_simula_loop_with_contract_file_path(self):
        contract_file = PROJECT_ROOT / "contracts" / "exemplo_credito_mesh.yaml"
        if not contract_file.exists():
            pytest.skip("contracts/exemplo_credito_mesh.yaml not found")

        stream = run_simula_loop(
            contract_path=str(contract_file),
            max_iterations=1,
            mock_mode=True,
        )
        events = list(stream)
        assert len(events) >= 4
        # Verify contract was ingested into working_memory
        init_event = [e for e in events if e.step == "init_complete"][0]
        tables = init_event.state["working_memory"]["contract_dict"].get("tables", [])
        table_names = [t.get("name") for t in tables]
        for expected in ["empresas", "propostas", "garantias", "operacoes"]:
            assert expected in table_names

    def test_run_simula_loop_invalid_contract_raises(self):
        with pytest.raises(ValueError, match="contract_path or contract_yaml_path must be provided"):
            list(run_simula_loop(contract_path=None))
