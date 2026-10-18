"""core/graph.py - LangGraph StateGraph & Event Streaming for CoALA Cognitive Loop.

Coordinates autonomous generation, regex/AST parsing, isolated sandbox execution,
and episodic memory feedback routing for relational data mock synthesis.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.code_parser import CodeParser
from core.llm_client import MockLLMClient, OpenRouterClient
from core.memory import create_initial_procedural_memory
from core.sandbox import PytestSandbox
from core.state import EpisodicMemoryRecord, SimulaEvent, SimulaState


def node_initialize(state: SimulaState) -> dict[str, Any]:
    """Node: Initialize state, parse contract YAML, load procedural memory rules."""
    raw_yaml = state.get("working_memory", {}).get("contract_yaml", "")
    contract_dict = {}
    if raw_yaml:
        try:
            contract_dict = yaml.safe_load(raw_yaml) or {}
        except yaml.YAMLError:
            contract_dict = {}

    procedural = state.get("procedural_memory")
    if not procedural or not isinstance(procedural, dict) or not procedural.get("faker_rules"):
        procedural = create_initial_procedural_memory()

    return {
        "working_memory": {
            **state.get("working_memory", {}),
            "contract_dict": contract_dict,
            "generated_code": state.get("working_memory", {}).get("generated_code"),
            "pytest_output": None,
            "pytest_exit_code": None,
            "last_error": None,
        },
        "procedural_memory": procedural,
        "episodic_memory": state.get("episodic_memory", []) or [],
        "iterations": 0,
        "max_iterations": state.get("max_iterations", 5),
        "status": "INIT",
        "error_message": None,
    }


def node_generate(state: SimulaState, llm_client: Any) -> dict[str, Any]:
    """Node: Synthesize candidate mock generator and tests using LLM client."""
    current_iter = state.get("iterations", 0) + 1
    raw_response = llm_client.generate_candidate(
        procedural_memory=state.get("procedural_memory", {}),
        working_memory=state.get("working_memory", {}),
        episodic_memory=state.get("episodic_memory", []),
        iteration=current_iter,
    )

    extracted_code = CodeParser.extract_python_code(raw_response)

    return {
        "working_memory": {
            **state.get("working_memory", {}),
            "generated_code": extracted_code,
        },
        "iterations": current_iter,
        "status": "GENERATING",
    }


def node_execute(state: SimulaState, sandbox: Any) -> dict[str, Any]:
    """Node: Execute generated code in an isolated subprocess Pytest sandbox."""
    code = state.get("working_memory", {}).get("generated_code") or ""
    result = sandbox.execute(code)

    exit_code = getattr(result, "exit_code", -1)
    stdout = getattr(result, "stdout", "")
    stderr = getattr(result, "stderr", "")
    error_summary = getattr(result, "error_summary", "")
    failed_tests = getattr(result, "failed_tests", []) or []
    is_success = getattr(result, "is_success", exit_code == 0)

    pytest_output = stdout + (("\n" + stderr) if stderr else "")
    current_iter = state.get("iterations", 1)
    max_iter = state.get("max_iterations", 5)

    updates: dict[str, Any] = {
        "working_memory": {
            **state.get("working_memory", {}),
            "pytest_output": pytest_output,
            "pytest_exit_code": exit_code,
            "last_error": error_summary or (stderr or stdout)[:1000],
        }
    }

    if is_success:
        updates["status"] = "SUCCESS"
        updates["episodic_memory"] = state.get("episodic_memory", [])
    else:
        new_record: EpisodicMemoryRecord = {
            "iteration": current_iter,
            "generated_code": code,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "error_summary": error_summary or (stderr or stdout)[:1000],
            "failed_tests": failed_tests,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        updates["episodic_memory"] = list(state.get("episodic_memory", [])) + [new_record]

        if current_iter >= max_iter:
            updates["status"] = "FAILED_MAX_RETRIES"
        else:
            updates["status"] = "RETRY"

    return updates


def route_decision(state: SimulaState) -> Literal["success", "failed_max_retries", "retry"]:
    """Conditional Edge: Determines transition target based on state.

    - exit_code == 0 (or status == 'SUCCESS') -> transitions to END with status SUCCESS
    - iterations >= max_iterations (or status == 'FAILED_MAX_RETRIES') -> transitions to END with status FAILED_MAX_RETRIES
    - test failure -> transitions back to node_generate
    """
    status = state.get("status")
    working = state.get("working_memory", {})
    pytest_exit_code = working.get("pytest_exit_code")
    iterations = state.get("iterations", 0)
    max_iterations = state.get("max_iterations", 5)

    if status == "SUCCESS" or pytest_exit_code == 0:
        return "success"
    if status == "FAILED_MAX_RETRIES" or iterations >= max_iterations:
        return "failed_max_retries"
    return "retry"


def create_simula_graph(llm_client: Any, sandbox: Any) -> CompiledStateGraph:
    """Constructs and compiles the CoALA StateGraph LangGraph application."""
    builder = StateGraph(SimulaState)

    builder.add_node("node_initialize", node_initialize)
    builder.add_node("node_generate", lambda state: node_generate(state, llm_client))
    builder.add_node("node_execute", lambda state: node_execute(state, sandbox))

    builder.add_edge(START, "node_initialize")
    builder.add_edge("node_initialize", "node_generate")
    builder.add_edge("node_generate", "node_execute")

    builder.add_conditional_edges(
        "node_execute",
        route_decision,
        {
            "success": END,
            "failed_max_retries": END,
            "retry": "node_generate",
        },
    )

    return builder.compile()


def run_simula_loop(
    contract_path: str | Path | None = None,
    max_iterations: int = 5,
    model: str = "nousresearch/hermes-3-llama-3.1-405b",
    mock_mode: bool = False,
    contract_yaml_path: str | Path | None = None,
    api_key: str | None = None,
    sandbox_timeout: int = 30,
    client: Any = None,
    sandbox: Any = None,
    on_step_callback: Callable[[SimulaEvent], None] | None = None,
    **kwargs: Any,
) -> Iterator[SimulaEvent]:
    """Event streaming generator running the full CoALA loop for CLI & Streamlit.

    Yields SimulaEvent instances at each lifecycle phase.
    """
    target = contract_path or contract_yaml_path
    if not target:
        raise ValueError("contract_path or contract_yaml_path must be provided.")

    if isinstance(target, (str, Path)) and Path(target).is_file():
        contract_yaml = Path(target).read_text(encoding="utf-8")
    elif isinstance(target, str):
        contract_yaml = target
    else:
        raise ValueError(f"Unable to read data contract from: {target}")

    state: SimulaState = {
        "procedural_memory": {},
        "working_memory": {
            "contract_yaml": contract_yaml,
            "contract_dict": {},
            "generated_code": None,
            "pytest_output": None,
            "pytest_exit_code": None,
            "last_error": None,
        },
        "episodic_memory": [],
        "iterations": 0,
        "max_iterations": max_iterations,
        "status": "INIT",
        "error_message": None,
    }

    if client is None:
        is_mock = mock_mode or os.environ.get("SIMULA_MOCK_LLM", "").lower() in ("true", "1", "yes")
        if is_mock:
            client = MockLLMClient()
        else:
            client = OpenRouterClient(model=model, api_key=api_key)

    if sandbox is None:
        sandbox = PytestSandbox(timeout_seconds=sandbox_timeout)

    # Step 1: Initialize
    ev_init = SimulaEvent(
        step="init_start",
        iteration=0,
        state=state,
        message="Initializing Simula-AI cognitive loop and ingesting data contract...",
    )
    if on_step_callback:
        on_step_callback(ev_init)
    yield ev_init

    init_updates = node_initialize(state)
    state = {**state, **init_updates}

    ev_init_done = SimulaEvent(
        step="init_complete",
        iteration=0,
        state=state,
        message="Data contract ingested, tables parsed, and procedural memory loaded.",
    )
    if on_step_callback:
        on_step_callback(ev_init_done)
    yield ev_init_done

    # Cognitive Loop
    while True:
        next_iter = state["iterations"] + 1

        ev_gen_start = SimulaEvent(
            step="generate_start",
            iteration=next_iter,
            state=state,
            message=f"Generating candidate mock generator & tests (iteration {next_iter}/{max_iterations})...",
        )
        if on_step_callback:
            on_step_callback(ev_gen_start)
        yield ev_gen_start

        gen_updates = node_generate(state, client)
        state = {**state, **gen_updates}
        code = state["working_memory"].get("generated_code") or ""

        ev_gen_done = SimulaEvent(
            step="generate_complete",
            iteration=state["iterations"],
            state=state,
            message=f"Synthesized candidate code ({len(code)} characters).",
        )
        if on_step_callback:
            on_step_callback(ev_gen_done)
        yield ev_gen_done

        ev_exec_start = SimulaEvent(
            step="execute_start",
            iteration=state["iterations"],
            state=state,
            message="Running isolated Pytest sandbox in temporary subprocess...",
        )
        if on_step_callback:
            on_step_callback(ev_exec_start)
        yield ev_exec_start

        exec_updates = node_execute(state, sandbox)
        state = {**state, **exec_updates}
        exit_code = state["working_memory"].get("pytest_exit_code")

        ev_exec_done = SimulaEvent(
            step="execute_complete",
            iteration=state["iterations"],
            state=state,
            message=f"Pytest execution finished with exit code {exit_code}.",
        )
        if on_step_callback:
            on_step_callback(ev_exec_done)
        yield ev_exec_done

        decision = route_decision(state)
        if decision == "success":
            ev_success = SimulaEvent(
                step="success",
                iteration=state["iterations"],
                state=state,
                message="Pytest validation passed with return code 0! Artifacts validated.",
            )
            if on_step_callback:
                on_step_callback(ev_success)
            yield ev_success
            break
        elif decision == "failed_max_retries":
            ev_fail = SimulaEvent(
                step="failed_max_retries",
                iteration=state["iterations"],
                state=state,
                message=f"Loop exhausted {max_iterations} retries without resolving test failures.",
                error=state["working_memory"].get("last_error"),
            )
            if on_step_callback:
                on_step_callback(ev_fail)
            yield ev_fail
            break
        else:  # retry
            ev_retry = SimulaEvent(
                step="retry",
                iteration=state["iterations"],
                state=state,
                message=f"Validation failed (exit code {exit_code}). Feeding error traceback into episodic memory for retry.",
            )
            if on_step_callback:
                on_step_callback(ev_retry)
            yield ev_retry
