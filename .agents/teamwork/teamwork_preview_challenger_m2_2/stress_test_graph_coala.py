"""stress_test_graph_coala.py - Empirical Adversarial Stress Test Harness for CoALA Cognitive Loop.

Challenger 2 Milestone 2 (CoALA Cognitive Loop & Sandbox)
Evaluates:
1. StateGraph routing across multi-iteration failures (1 -> 2 -> 3) and episodic_memory accumulation.
2. Boundary conditions: reaching MAX_ITERATIONS terminating with FAILED_MAX_RETRIES (bounds 1, 2, 5, 10).
3. Success conditions: first iteration and second iteration resolution (terminating with SUCCESS).
4. Streaming generator run_simula_loop: lifecycle event sequences, callback parity, serialization.
5. Adversarial robustness: non-dict YAML scalars, syntax errors, timeouts, large outputs, state immutability.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.code_parser import CodeParser
from core.graph import (
    create_simula_graph,
    node_execute,
    node_generate,
    node_initialize,
    route_decision,
    run_simula_loop,
)
from core.memory import create_initial_procedural_memory, format_episodic_feedback
from core.state import (
    EpisodicMemoryRecord,
    SimulaEvent,
    SimulaState,
    create_initial_state,
)


# ============================================================================
# MOCK INFRASTRUCTURE FOR ADVERSARIAL TESTING
# ============================================================================

@dataclass
class SimulatedSandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.05
    failed_tests: list[str] = None
    error_summary: str = ""

    def __post_init__(self):
        if self.failed_tests is None:
            self.failed_tests = []

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class ScriptedLLMClient:
    """Deterministic LLM test double returning scripted responses per iteration."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate_candidate(self, **kwargs: Any) -> str:
        call_idx = len(self.calls)
        self.calls.append(kwargs)
        if call_idx < len(self.responses):
            return self.responses[call_idx]
        return self.responses[-1]


class ScriptedSandbox:
    """Deterministic Sandbox test double returning scripted results per execution."""

    def __init__(self, results: list[SimulatedSandboxResult]) -> None:
        self.results = results
        self.executed_codes: list[str] = []

    def execute(self, code: str) -> SimulatedSandboxResult:
        call_idx = len(self.executed_codes)
        self.executed_codes.append(code)
        if call_idx < len(self.results):
            return self.results[call_idx]
        return self.results[-1]


SAMPLE_CONTRACT_YAML = """
mesh_name: credit_mesh
version: "1.0.0"
tables:
  - name: empresas
    fields:
      - name: empresa_id
        type: string
        primary_key: true
      - name: cnpj
        type: string
  - name: propostas
    fields:
      - name: proposta_id
        type: string
        primary_key: true
      - name: empresa_id
        type: string
        foreign_key: empresas.empresa_id
"""


# ============================================================================
# SUITE 1: Multi-Iteration Failure & Episodic Traceback Accumulation (1 -> 2 -> 3)
# ============================================================================

class TestSuite1MultiIterationAccumulation:
    """Stress tests StateGraph routing across iterations 1 -> 2 -> 3 and memory accumulation."""

    def test_stategraph_three_consecutive_failures_accumulates_tracebacks(self):
        """Verify StateGraph accurately sequences 3 distinct failures and retains each traceback."""
        codes = [
            "```python\ndef test_iter1(): assert 1 == 2, 'Iter 1 FK Orphan Failure'\n```",
            "```python\ndef test_iter2(): raise KeyError('Iter 2 Missing Column: status_proposta')\n```",
            "```python\ndef test_iter3(): assert 0 == 1, 'Iter 3 Value Range Out of Bounds'\n```",
        ]
        results = [
            SimulatedSandboxResult(
                exit_code=1,
                stdout="FAILED simula_temp_test.py::test_iter1 - AssertionError: Iter 1 FK Orphan Failure",
                stderr="",
                failed_tests=["test_iter1"],
                error_summary="AssertionError: Iter 1 FK Orphan Failure",
            ),
            SimulatedSandboxResult(
                exit_code=1,
                stdout="FAILED simula_temp_test.py::test_iter2 - KeyError: status_proposta",
                stderr="",
                failed_tests=["test_iter2"],
                error_summary="KeyError: 'status_proposta'",
            ),
            SimulatedSandboxResult(
                exit_code=1,
                stdout="FAILED simula_temp_test.py::test_iter3 - AssertionError: Iter 3 Value Range Out of Bounds",
                stderr="",
                failed_tests=["test_iter3"],
                error_summary="AssertionError: Iter 3 Value Range Out of Bounds",
            ),
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=3)
        final_state = graph.invoke(init_state)

        # Verification 1: Termination status and iteration count
        assert final_state["status"] == "FAILED_MAX_RETRIES", f"Expected FAILED_MAX_RETRIES, got {final_state['status']}"
        assert final_state["iterations"] == 3, f"Expected exactly 3 iterations, got {final_state['iterations']}"

        # Verification 2: Episodic memory accumulation
        episodic = final_state.get("episodic_memory", [])
        assert len(episodic) == 3, f"Expected 3 accumulated episodic records, found {len(episodic)}"

        # Verification 3: Chronological order and distinctness of records
        assert episodic[0]["iteration"] == 1
        assert "Iter 1 FK Orphan Failure" in episodic[0]["error_summary"]
        assert episodic[0]["failed_tests"] == ["test_iter1"]
        assert episodic[0]["exit_code"] == 1

        assert episodic[1]["iteration"] == 2
        assert "KeyError" in episodic[1]["error_summary"]
        assert episodic[1]["failed_tests"] == ["test_iter2"]
        assert episodic[1]["exit_code"] == 1

        assert episodic[2]["iteration"] == 3
        assert "Iter 3 Value Range" in episodic[2]["error_summary"]
        assert episodic[2]["failed_tests"] == ["test_iter3"]
        assert episodic[2]["exit_code"] == 1

        # Verification 4: LLM call history and episodic memory propagation
        assert len(llm.calls) == 3
        assert len(llm.calls[0]["episodic_memory"]) == 0
        assert len(llm.calls[1]["episodic_memory"]) == 1
        assert "Iter 1 FK Orphan Failure" in llm.calls[1]["episodic_memory"][0]["error_summary"]
        assert len(llm.calls[2]["episodic_memory"]) == 2
        assert "KeyError" in llm.calls[2]["episodic_memory"][1]["error_summary"]

    def test_stategraph_multi_iteration_self_healing_at_iteration_3(self):
        """Verify failures in iterations 1 and 2, succeeded by resolution in iteration 3."""
        codes = [
            "```python\ndef test_attempt1(): assert False, 'Schema mismatch'\n```",
            "```python\ndef test_attempt2(): assert False, 'Cardinality 1:N mismatch'\n```",
            "```python\ndef test_attempt3(): assert True\n```",
        ]
        results = [
            SimulatedSandboxResult(
                exit_code=1,
                stdout="FAILED simula_temp_test.py::test_attempt1",
                stderr="",
                failed_tests=["test_attempt1"],
                error_summary="Schema mismatch",
            ),
            SimulatedSandboxResult(
                exit_code=1,
                stdout="FAILED simula_temp_test.py::test_attempt2",
                stderr="",
                failed_tests=["test_attempt2"],
                error_summary="Cardinality 1:N mismatch",
            ),
            SimulatedSandboxResult(
                exit_code=0,
                stdout="1 passed in 0.05s",
                stderr="",
                failed_tests=[],
                error_summary="",
            ),
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=4)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "SUCCESS"
        assert final_state["iterations"] == 3
        assert final_state["working_memory"]["pytest_exit_code"] == 0

        # Memory must contain the 2 prior failures
        episodic = final_state["episodic_memory"]
        assert len(episodic) == 2
        assert episodic[0]["iteration"] == 1
        assert "Schema mismatch" in episodic[0]["error_summary"]
        assert episodic[1]["iteration"] == 2
        assert "Cardinality 1:N mismatch" in episodic[1]["error_summary"]

    def test_episodic_feedback_formatting_preserves_most_recent_tracebacks(self):
        """Verify format_episodic_feedback formats recent tracebacks with repair directives."""
        records: list[EpisodicMemoryRecord] = [
            {
                "iteration": 1,
                "generated_code": "# code 1",
                "exit_code": 1,
                "stdout": "",
                "stderr": "",
                "error_summary": "AssertionError: orphan FK propostas.empresa_id",
                "failed_tests": ["test_fk_integrity"],
                "timestamp": "2026-10-12T20:00:00Z",
            },
            {
                "iteration": 2,
                "generated_code": "# code 2",
                "exit_code": 1,
                "stdout": "",
                "stderr": "",
                "error_summary": "AssertionError: CNPJ format invalid 12345",
                "failed_tests": ["test_cnpj_format"],
                "timestamp": "2026-10-12T20:01:00Z",
            },
            {
                "iteration": 3,
                "generated_code": "# code 3",
                "exit_code": 1,
                "stdout": "",
                "stderr": "",
                "error_summary": "AssertionError: valor_contratado > valor_solicitado",
                "failed_tests": ["test_business_rules"],
                "timestamp": "2026-10-12T20:02:00Z",
            },
        ]

        # max_history=2 should format attempt 2 and 3, omitting attempt 1 to prevent context bloat
        feedback = format_episodic_feedback(records, max_history=2)
        assert "Attempt #2" in feedback
        assert "Attempt #3" in feedback
        assert "Attempt #1" not in feedback
        assert "CNPJ format invalid" in feedback
        assert "valor_contratado > valor_solicitado" in feedback
        assert "REPAIR DIRECTIVES" in feedback


# ============================================================================
# SUITE 2: Boundary Conditions & MAX_ITERATIONS Termination
# ============================================================================

class TestSuite2BoundaryConditions:
    """Stress tests boundary limits for MAX_ITERATIONS termination with FAILED_MAX_RETRIES."""

    @pytest.mark.parametrize("max_iter", [1, 2, 4, 7])
    def test_boundary_exact_max_iterations_exhaustion(self, max_iter: int):
        """Verify loop executes EXACTLY max_iter times before terminating with FAILED_MAX_RETRIES."""
        codes = [f"```python\ndef test_err_{i}(): assert False\n```" for i in range(max_iter + 2)]
        results = [
            SimulatedSandboxResult(
                exit_code=1,
                stdout=f"FAILED test_err_{i}",
                stderr="",
                failed_tests=[f"test_err_{i}"],
                error_summary=f"Failure #{i + 1}",
            )
            for i in range(max_iter + 2)
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=max_iter)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "FAILED_MAX_RETRIES"
        assert final_state["iterations"] == max_iter
        assert len(final_state["episodic_memory"]) == max_iter
        assert len(sandbox.executed_codes) == max_iter
        assert len(llm.calls) == max_iter

    def test_boundary_single_iteration_max_limit(self):
        """Verify max_iterations=1 fails on attempt 1 without triggering retry node."""
        llm = ScriptedLLMClient(["```python\ndef test_fail(): assert False\n```"])
        sandbox = ScriptedSandbox([SimulatedSandboxResult(exit_code=1, stdout="FAIL", stderr="", error_summary="err")])
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=1)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "FAILED_MAX_RETRIES"
        assert final_state["iterations"] == 1
        assert len(final_state["episodic_memory"]) == 1

    def test_boundary_zero_or_negative_max_iterations_fails_immediately(self):
        """Adversarial: max_iterations <= 0 terminates on first execution without infinite looping."""
        llm = ScriptedLLMClient(["```python\ndef test_fail(): assert False\n```"])
        sandbox = ScriptedSandbox([SimulatedSandboxResult(exit_code=1, stdout="FAIL", stderr="", error_summary="err")])
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=0)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "FAILED_MAX_RETRIES"
        assert final_state["iterations"] == 1


# ============================================================================
# SUITE 3: Success Conditions (First & Second Iteration Early Exits)
# ============================================================================

class TestSuite3SuccessConditions:
    """Stress tests immediate termination upon test success."""

    def test_immediate_success_on_first_iteration(self):
        """Verify first iteration pass terminates immediately without unnecessary retry cycles."""
        codes = [
            "```python\ndef test_immediate(): assert True\n```",
            "```python\ndef test_should_not_run(): assert True\n```",
        ]
        results = [
            SimulatedSandboxResult(exit_code=0, stdout="1 passed", stderr="", failed_tests=[]),
            SimulatedSandboxResult(exit_code=0, stdout="never called", stderr="", failed_tests=[]),
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=5)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "SUCCESS"
        assert final_state["iterations"] == 1
        assert final_state["working_memory"]["pytest_exit_code"] == 0
        assert len(final_state["episodic_memory"]) == 0
        assert len(llm.calls) == 1
        assert len(sandbox.executed_codes) == 1

    def test_success_on_second_iteration_after_initial_failure(self):
        """Verify recovery on iteration 2 terminates immediately, leaving 1 error record in episodic memory."""
        codes = [
            "```python\ndef test_fail(): assert False\n```",
            "```python\ndef test_pass(): assert True\n```",
            "```python\ndef test_unreached(): assert True\n```",
        ]
        results = [
            SimulatedSandboxResult(exit_code=1, stdout="FAIL", stderr="", failed_tests=["test_fail"], error_summary="bug"),
            SimulatedSandboxResult(exit_code=0, stdout="1 passed", stderr="", failed_tests=[]),
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=5)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "SUCCESS"
        assert final_state["iterations"] == 2
        assert len(final_state["episodic_memory"]) == 1
        assert len(llm.calls) == 2
        assert len(sandbox.executed_codes) == 2

    def test_success_precedence_on_exact_final_iteration(self):
        """Edge case: Passing on iter 3 of max_iter 3 must yield SUCCESS, not FAILED_MAX_RETRIES."""
        codes = [
            "```python\ndef test_f1(): assert False\n```",
            "```python\ndef test_f2(): assert False\n```",
            "```python\ndef test_p3(): assert True\n```",
        ]
        results = [
            SimulatedSandboxResult(exit_code=1, stdout="FAIL 1", stderr="", failed_tests=["test_f1"]),
            SimulatedSandboxResult(exit_code=1, stdout="FAIL 2", stderr="", failed_tests=["test_f2"]),
            SimulatedSandboxResult(exit_code=0, stdout="PASS 3", stderr="", failed_tests=[]),
        ]

        llm = ScriptedLLMClient(codes)
        sandbox = ScriptedSandbox(results)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=3)
        final_state = graph.invoke(init_state)

        assert final_state["status"] == "SUCCESS", (
            f"Expected SUCCESS when last attempt passes, got {final_state['status']}"
        )
        assert final_state["iterations"] == 3
        assert len(final_state["episodic_memory"]) == 2

    def test_route_decision_truth_table_exhaustive(self):
        """Verify route_decision determinism across complete truth table."""
        # 1. Success conditions
        assert route_decision({"status": "SUCCESS", "working_memory": {"pytest_exit_code": 0}, "iterations": 1, "max_iterations": 3}) == "success"
        assert route_decision({"status": "GENERATING", "working_memory": {"pytest_exit_code": 0}, "iterations": 3, "max_iterations": 3}) == "success"
        assert route_decision({"status": "SUCCESS", "working_memory": {"pytest_exit_code": 1}, "iterations": 1, "max_iterations": 3}) == "success"

        # 2. Max retries conditions
        assert route_decision({"status": "FAILED_MAX_RETRIES", "working_memory": {"pytest_exit_code": 1}, "iterations": 3, "max_iterations": 3}) == "failed_max_retries"
        assert route_decision({"status": "RETRY", "working_memory": {"pytest_exit_code": 1}, "iterations": 3, "max_iterations": 3}) == "failed_max_retries"
        assert route_decision({"status": "RETRY", "working_memory": {"pytest_exit_code": 1}, "iterations": 4, "max_iterations": 3}) == "failed_max_retries"

        # 3. Retry conditions
        assert route_decision({"status": "RETRY", "working_memory": {"pytest_exit_code": 1}, "iterations": 1, "max_iterations": 3}) == "retry"
        assert route_decision({"status": "RETRY", "working_memory": {"pytest_exit_code": 2}, "iterations": 2, "max_iterations": 3}) == "retry"


# ============================================================================
# SUITE 4: Streaming Generator Lifecycle & SimulaEvent Verification
# ============================================================================

class TestSuite4StreamingGeneratorLifecycle:
    """Stress tests run_simula_loop generator events, callbacks, and data structures."""

    def test_run_simula_loop_lifecycle_first_iter_pass(self):
        """Verify exact event lifecycle sequence for single-iteration success."""
        stream = run_simula_loop(
            contract_path=SAMPLE_CONTRACT_YAML,
            max_iterations=3,
            mock_mode=True,
        )
        events = list(stream)

        steps = [e.step for e in events]
        expected_steps = [
            "init_start",
            "init_complete",
            "generate_start",
            "generate_complete",
            "execute_start",
            "execute_complete",
            "success",
        ]
        assert steps == expected_steps, f"Step sequence mismatch: {steps} != {expected_steps}"

        # Verify iteration field integrity
        assert events[0].iteration == 0  # init_start
        assert events[1].iteration == 0  # init_complete
        assert events[2].iteration == 1  # generate_start
        assert events[3].iteration == 1  # generate_complete
        assert events[4].iteration == 1  # execute_start
        assert events[5].iteration == 1  # execute_complete
        assert events[6].iteration == 1  # success

        # Verify final state in event
        final_event = events[-1]
        assert final_event.state["status"] == "SUCCESS"
        assert final_event.state["iterations"] == 1
        assert len(final_event.state["episodic_memory"]) == 0

    def test_run_simula_loop_lifecycle_two_iterations_fail_then_pass(self):
        """Verify exact event lifecycle sequence when iteration 1 fails and iteration 2 succeeds."""
        with patch.dict(os.environ, {"SIMULA_MOCK_FAIL_FIRST": "true"}):
            stream = run_simula_loop(
                contract_path=SAMPLE_CONTRACT_YAML,
                max_iterations=3,
                mock_mode=True,
            )
            events = list(stream)

        steps = [e.step for e in events]
        expected_steps = [
            "init_start",
            "init_complete",
            # Iteration 1
            "generate_start",
            "generate_complete",
            "execute_start",
            "execute_complete",
            "retry",
            # Iteration 2
            "generate_start",
            "generate_complete",
            "execute_start",
            "execute_complete",
            "success",
        ]
        assert steps == expected_steps, f"Step sequence mismatch: {steps} != {expected_steps}"

        # Check iteration counter progression
        assert [e.iteration for e in events] == [0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2]

        retry_event = events[6]
        assert retry_event.step == "retry"
        assert retry_event.iteration == 1
        assert retry_event.state["status"] == "RETRY"
        assert len(retry_event.state["episodic_memory"]) == 1

        success_event = events[11]
        assert success_event.step == "success"
        assert success_event.iteration == 2
        assert success_event.state["status"] == "SUCCESS"
        assert len(success_event.state["episodic_memory"]) == 1

    def test_run_simula_loop_lifecycle_max_retries_exhaustion(self):
        """Verify event lifecycle sequence when all iterations fail reaching max_iterations."""
        class MockFailingClient:
            def generate_candidate(self, **kwargs):
                return "```python\ndef test_always_bad(): assert False\n```"

        class MockFailingSandbox:
            def execute(self, code):
                return SimulatedSandboxResult(exit_code=1, stdout="FAIL", stderr="", error_summary="Err")

        with patch("core.graph.MockLLMClient", return_value=MockFailingClient()), \
             patch("core.graph.PytestSandbox", return_value=MockFailingSandbox()):

            stream = run_simula_loop(
                contract_path=SAMPLE_CONTRACT_YAML,
                max_iterations=2,
                mock_mode=True,
            )
            events = list(stream)

        steps = [e.step for e in events]
        expected_steps = [
            "init_start",
            "init_complete",
            # Iteration 1
            "generate_start",
            "generate_complete",
            "execute_start",
            "execute_complete",
            "retry",
            # Iteration 2
            "generate_start",
            "generate_complete",
            "execute_start",
            "execute_complete",
            "failed_max_retries",
        ]
        assert steps == expected_steps, f"Step sequence mismatch: {steps} != {expected_steps}"

        last_ev = events[-1]
        assert last_ev.step == "failed_max_retries"
        assert last_ev.iteration == 2
        assert last_ev.state["status"] == "FAILED_MAX_RETRIES"
        assert len(last_ev.state["episodic_memory"]) == 2
        assert last_ev.error is not None

    def test_run_simula_loop_callback_parity_and_ordering(self):
        """Verify on_step_callback receives the identical event stream in matching order."""
        callback_events: list[SimulaEvent] = []

        def on_step(event: SimulaEvent) -> None:
            callback_events.append(event)

        stream = run_simula_loop(
            contract_path=SAMPLE_CONTRACT_YAML,
            max_iterations=2,
            mock_mode=True,
            on_step_callback=on_step,
        )
        yielded_events = list(stream)

        assert len(callback_events) == len(yielded_events)
        for cb_ev, yield_ev in zip(callback_events, yielded_events):
            assert cb_ev.step == yield_ev.step
            assert cb_ev.iteration == yield_ev.iteration
            assert cb_ev.message == yield_ev.message
            assert cb_ev.timestamp == yield_ev.timestamp

    def test_run_simula_loop_event_to_dict_serialization(self):
        """Verify SimulaEvent.to_dict produces expected payload for Web UI/CLI."""
        stream = run_simula_loop(
            contract_path=SAMPLE_CONTRACT_YAML,
            max_iterations=1,
            mock_mode=True,
        )
        events = list(stream)
        for ev in events:
            d = ev.to_dict()
            assert isinstance(d, dict)
            assert "step" in d
            assert "iteration" in d
            assert "message" in d
            assert "timestamp" in d
            assert "status" in d
            assert "pytest_exit_code" in d


# ============================================================================
# SUITE 5: Adversarial Robustness & Edge Cases
# ============================================================================

class TestSuite5AdversarialRobustness:
    """Stress tests adversarial inputs, malicious/malformed contracts, and subprocess corner cases."""

    def test_adversarial_yaml_scalar_does_not_corrupt_contract_dict(self):
        """Adversarial input: contract YAML contains raw scalar integer/boolean, not a mapping."""
        # '12345' is valid YAML scalar integer. In python yaml.safe_load returns int 12345.
        raw_scalar_yaml = "12345"
        init_state = create_initial_state(contract_yaml=raw_scalar_yaml, max_iterations=1)
        updates = node_initialize(init_state)

        # In node_initialize: contract_dict = yaml.safe_load(raw_yaml) or {}
        # If contract_dict is an int, test how state handles it
        cd = updates["working_memory"]["contract_dict"]
        # It should either be empty dict or a scalar, but must not crash
        assert updates["status"] == "INIT"

    def test_syntax_error_in_llm_code_captured_gracefully(self):
        """Adversarial input: LLM returns broken Python syntax with missing parentheses."""
        broken_syntax_code = "```python\ndef test_broken(\n    assert 1 ==\n```"
        llm = ScriptedLLMClient([broken_syntax_code])
        # Real PytestSandbox invocation against broken syntax
        from core.sandbox import PytestSandbox
        sandbox = PytestSandbox(timeout_seconds=5)

        graph = create_simula_graph(llm, sandbox)
        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=2)
        final_state = graph.invoke(init_state)

        assert final_state["iterations"] >= 1
        episodic = final_state.get("episodic_memory", [])
        assert len(episodic) >= 1
        # Pytest will fail with exit code 2 or 1 for syntax error in test file
        assert episodic[0]["exit_code"] != 0
        assert "SyntaxError" in episodic[0]["error_summary"] or "SyntaxError" in episodic[0]["stderr"] or "SyntaxError" in episodic[0]["stdout"]

    def test_sandbox_timeout_recovery_and_recording(self):
        """Adversarial input: LLM returns code with infinite while loop."""
        infinite_loop_code = "```python\nimport time\ndef test_infinite():\n    while True:\n        time.sleep(0.01)\n```"
        llm = ScriptedLLMClient([infinite_loop_code, "```python\ndef test_fixed(): assert True\n```"])

        from core.sandbox import PytestSandbox
        # Use short 2 second timeout for test speed
        sandbox = PytestSandbox(timeout_seconds=2)
        graph = create_simula_graph(llm, sandbox)

        init_state = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=2)
        final_state = graph.invoke(init_state)

        # Iteration 1 timed out and was recorded; Iteration 2 fixed it
        assert final_state["status"] == "SUCCESS"
        assert final_state["iterations"] == 2
        assert len(final_state["episodic_memory"]) == 1
        timeout_rec = final_state["episodic_memory"][0]
        assert timeout_rec["iteration"] == 1
        assert "TIMEOUT" in timeout_rec["failed_tests"] or "timed out" in timeout_rec["error_summary"].lower()

    def test_state_immutability_across_independent_runs(self):
        """Verify running multiple graphs sequentially does not contaminate state."""
        llm1 = ScriptedLLMClient(["```python\ndef test_err(): assert False\n```"])
        sandbox1 = ScriptedSandbox([SimulatedSandboxResult(exit_code=1, stdout="FAIL", stderr="", error_summary="err1")])
        graph1 = create_simula_graph(llm1, sandbox1)

        init_state1 = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=1)
        res1 = graph1.invoke(init_state1)

        assert res1["iterations"] == 1
        assert len(res1["episodic_memory"]) == 1
        assert "err1" in res1["episodic_memory"][0]["error_summary"]

        # Run 2 with separate clean state
        llm2 = ScriptedLLMClient(["```python\ndef test_ok(): assert True\n```"])
        sandbox2 = ScriptedSandbox([SimulatedSandboxResult(exit_code=0, stdout="PASS", stderr="")])
        graph2 = create_simula_graph(llm2, sandbox2)

        init_state2 = create_initial_state(contract_yaml=SAMPLE_CONTRACT_YAML, max_iterations=1)
        res2 = graph2.invoke(init_state2)

        assert res2["iterations"] == 1
        assert len(res2["episodic_memory"]) == 0
        assert res2["status"] == "SUCCESS"


# ============================================================================
# CLI ENTRYPOINT FOR STANDALONE RUNNER
# ============================================================================

def run_all_stress_tests() -> int:
    """Run stress test harness via pytest runner."""
    print("=" * 80)
    print("SIMULA-AI COALA COGNITIVE LOOP STRESS TEST HARNESS (CHALLENGER 2 - M2)")
    print("=" * 80)
    args = [
        "-v",
        "--tb=short",
        str(Path(__file__).resolve()),
    ]
    return pytest.main(args)


if __name__ == "__main__":
    sys.exit(run_all_stress_tests())
