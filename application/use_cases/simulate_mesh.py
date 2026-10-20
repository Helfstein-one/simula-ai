"""application/use_cases/simulate_mesh.py - Primary Use Case orchestrating the CoALA cognitive loop."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from application.ports.contract_port import ContractParserPort
from application.ports.llm_port import LLMProviderPort
from application.ports.sandbox_port import CodeSandboxPort
from application.ports.state_repository_port import StateRepositoryPort
from domain.ast_validator import DomainASTValidator
from domain.entities import DataContract
from domain.events import SimulaEvent
from domain.grounding import DomainTemplateGrounding
from domain.state import EpisodicMemoryRecord, SimulaState


class SimulateMeshUseCase:
    """Use Case coordinating the autonomous CoALA loop to mock relational Data Mesh ecosystems."""

    def __init__(
        self,
        llm_provider: LLMProviderPort,
        sandbox: CodeSandboxPort,
        contract_parser: ContractParserPort,
        state_repository: Optional[StateRepositoryPort] = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.sandbox = sandbox
        self.contract_parser = contract_parser
        self.state_repository = state_repository

    def execute_stream(
        self,
        contract_source: str | Path | Dict[str, Any] | DataContract,
        max_iterations: int = 5,
        session_id: Optional[str] = None,
        on_step_callback: Optional[Callable[[SimulaEvent], None]] = None,
    ) -> Iterator[SimulaEvent]:
        """Runs the CoALA cognitive loop, yielding SimulaEvent lifecycle events."""
        current_session_id = session_id or uuid.uuid4().hex[:12]
        # 1. Ingest Contract
        if isinstance(contract_source, DataContract):
            contract = contract_source
            raw_yaml = contract.to_yaml() if hasattr(contract, "to_yaml") else ""
        elif isinstance(contract_source, (str, Path)) and Path(contract_source).is_file():
            raw_yaml = Path(contract_source).read_text(encoding="utf-8")
            contract = self.contract_parser.parse(raw_yaml)
        elif isinstance(contract_source, str):
            raw_yaml = contract_source
            contract = self.contract_parser.parse(raw_yaml)
        elif isinstance(contract_source, dict):
            contract = self.contract_parser.parse(contract_source)
            raw_yaml = contract.to_yaml() if hasattr(contract, "to_yaml") else ""
        else:
            raise ValueError(f"Unsupported contract source type: {type(contract_source)}")

        # 2. Extract Kahn DAG grounding
        scaffolding = DomainTemplateGrounding.generate_scaffolding(contract)

        state: SimulaState = {
            "procedural_memory": {
                "scaffolding": scaffolding,
                "dag_order": contract.topological_sort() if hasattr(contract, "topological_sort") else [],
            },
            "working_memory": {
                "contract_yaml": raw_yaml,
                "contract_dict": contract.model_dump() if hasattr(contract, "model_dump") else {},
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

        # Step: Init start
        ev_init = SimulaEvent(
            step="init_start",
            iteration=0,
            state=state,
            message="Initializing Simula-AI CoALA loop and ingesting data contract...",
        )
        if on_step_callback:
            on_step_callback(ev_init)
        yield ev_init

        # Step: Init complete
        ev_init_done = SimulaEvent(
            step="init_complete",
            iteration=0,
            state=state,
            message=f"Contract '{contract.name}' ingested ({len(contract.tables)} tables). Kahn DAG sequence computed.",
        )
        if on_step_callback:
            on_step_callback(ev_init_done)
        if self.state_repository:
            self.state_repository.save_checkpoint(current_session_id, 0, state, status="INIT", message=ev_init_done.message)
        yield ev_init_done

        # 3. Cognitive Loop
        while True:
            next_iter = state["iterations"] + 1

            ev_gen_start = SimulaEvent(
                step="generate_start",
                iteration=next_iter,
                state=state,
                message=f"Synthesizing candidate generator & tests (iteration {next_iter}/{max_iterations})...",
            )
            if on_step_callback:
                on_step_callback(ev_gen_start)
            yield ev_gen_start

            # Generate via LLM
            generated_code = self.llm_provider.generate_candidate(
                procedural_memory=state.get("procedural_memory", {}),
                working_memory=state.get("working_memory", {}),
                episodic_memory=state.get("episodic_memory", []),
                iteration=next_iter,
            )

            state["working_memory"]["generated_code"] = generated_code
            state["iterations"] = next_iter
            state["status"] = "GENERATING"

            ev_gen_done = SimulaEvent(
                step="generate_complete",
                iteration=next_iter,
                state=state,
                message=f"Candidate code synthesized ({len(generated_code)} characters).",
            )
            if on_step_callback:
                on_step_callback(ev_gen_done)
            yield ev_gen_done

            # Pre-flight In-Memory AST Validation
            ast_report = DomainASTValidator.analyze_structure(generated_code)

            ev_exec_start = SimulaEvent(
                step="execute_start",
                iteration=next_iter,
                state=state,
                message="Running isolated Pytest sandbox in temporary subprocess...",
            )
            if on_step_callback:
                on_step_callback(ev_exec_start)
            yield ev_exec_start

            if not ast_report.is_valid:
                # Early catch before subprocess execution
                exit_code = 1
                stdout = ""
                stderr = f"AST Pre-Flight Validation Error: {ast_report.error_message}"
                error_summary = stderr
                failed_tests = [ast_report.error_message or "ASTValidationError"]
                is_success = False
            else:
                # Subprocess sandbox execution
                sandbox_result = self.sandbox.execute(generated_code)
                exit_code = sandbox_result.exit_code
                stdout = sandbox_result.stdout
                stderr = sandbox_result.stderr
                error_summary = getattr(sandbox_result, "error_summary", stderr or stdout[:500])
                failed_tests = getattr(sandbox_result, "failed_tests", []) or []
                is_success = sandbox_result.is_success

            pytest_output = stdout + (("\n" + stderr) if stderr else "")
            state["working_memory"]["pytest_output"] = pytest_output
            state["working_memory"]["pytest_exit_code"] = exit_code
            state["working_memory"]["last_error"] = error_summary

            ev_exec_done = SimulaEvent(
                step="execute_complete",
                iteration=next_iter,
                state=state,
                message=f"Pytest execution finished with exit code {exit_code}.",
            )
            if on_step_callback:
                on_step_callback(ev_exec_done)
            yield ev_exec_done

            if is_success:
                state["status"] = "SUCCESS"
                ev_success = SimulaEvent(
                    step="success",
                    iteration=next_iter,
                    state=state,
                    message="Pytest validation passed with return code 0! Referential integrity guaranteed.",
                )
                if on_step_callback:
                    on_step_callback(ev_success)
                if self.state_repository:
                    self.state_repository.save_checkpoint(current_session_id, next_iter, state, status="SUCCESS", message=ev_success.message)
                yield ev_success
                break
            else:
                new_record: EpisodicMemoryRecord = {
                    "iteration": next_iter,
                    "generated_code": generated_code,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error_summary": error_summary,
                    "failed_tests": failed_tests,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                state["episodic_memory"].append(new_record)

                if next_iter >= max_iterations:
                    state["status"] = "FAILED_MAX_RETRIES"
                    ev_fail = SimulaEvent(
                        step="failed_max_retries",
                        iteration=next_iter,
                        state=state,
                        message=f"Loop exhausted {max_iterations} retries without resolving test failures.",
                        error=error_summary,
                    )
                    if on_step_callback:
                        on_step_callback(ev_fail)
                    if self.state_repository:
                        self.state_repository.save_checkpoint(current_session_id, next_iter, state, status="FAILED_MAX_RETRIES", message=ev_fail.message)
                    yield ev_fail
                    break
                else:
                    state["status"] = "RETRY"
                    ev_retry = SimulaEvent(
                        step="retry",
                        iteration=next_iter,
                        state=state,
                        message=f"Validation failed (exit code {exit_code}). Feeding traceback into episodic memory for Hermes self-correction.",
                    )
                    if on_step_callback:
                        on_step_callback(ev_retry)
                    if self.state_repository:
                        self.state_repository.save_checkpoint(current_session_id, next_iter, state, status="RETRY", message=ev_retry.message)
                    yield ev_retry

    def execute(
        self,
        contract_source: str | Path | Dict[str, Any] | DataContract,
        max_iterations: int = 5,
    ) -> SimulaState:
        """Executes the loop synchronously and returns the final state."""
        final_state: SimulaState = {}
        for ev in self.execute_stream(contract_source=contract_source, max_iterations=max_iterations):
            final_state = ev.state
        return final_state
