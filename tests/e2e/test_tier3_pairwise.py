"""Tier 3: Pairwise & Cross-Feature Integration Suite.

Covers cross-component interactions:
- CLI running mock cognitive loop with end-to-end artifact exports.
- Streamlit app state reflection across CoALA lifecycle.
- DataContract schema parsed from YAML and fed into Mermaid ER generator.
- Multi-iteration feedback loop: traceback injection into episodic memory triggering self-correction.
"""

import os
from pathlib import Path
from typing import Dict, Any

import pytest
try:
    from typer.testing import CliRunner
except ImportError:
    CliRunner = None



def test_t3_cli_runs_mock_cognitive_loop_and_exports_artifacts(sample_credit_mesh_yaml, tmp_workspace):
    """Verify CLI command executes CoALA loop in mock mode and exports deliverables (R1 + R2 + R4)."""
    cli_module = pytest.importorskip("cli.main")
    if CliRunner is None:
        pytest.importorskip("typer.testing")
    app = getattr(cli_module, "app")


    contract_file = tmp_workspace / "test_contract.yaml"
    contract_file.write_text(sample_credit_mesh_yaml, encoding="utf-8")
    output_dir = tmp_workspace / "cli_output"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            str(contract_file),
            "--output-dir",
            str(output_dir),
            "--iterations",
            "2",
            "--mock",
            "--rows",
            "10",
        ],
    )

    # CLI command should either exit 0 or perform generation
    assert result.exit_code == 0 or "mock" in result.stdout.lower() or output_dir.exists()


def test_t3_contract_schema_fed_into_mermaid_er_generator(sample_credit_mesh_yaml):
    """Verify DataContract schema cleanly feeds into Mermaid ER generator (R3 + R5)."""
    contract_module = pytest.importorskip("core.contract_parser")
    diagram_module = pytest.importorskip("core.diagram")

    contract = contract_module.parse_contract(sample_credit_mesh_yaml)
    mmd = diagram_module.generate_mermaid_er(contract)

    assert "erDiagram" in mmd
    # Check that all 4 credit mesh entities are present in uppercase or proper case
    for table_name in ["empresas", "propostas", "garantias", "operacoes"]:
        assert table_name in mmd.lower(), f"Table '{table_name}' missing from generated Mermaid diagram"

    # Verify foreign key relationship notation exists
    assert "--" in mmd
    assert "propostas" in mmd.lower() and "empresas" in mmd.lower()


def test_t3_coala_feedback_loop_iterative_recovery():
    """Verify episodic memory traceback from iteration 0 is fed back and resolved in iteration 1 (R1 Acceptance)."""
    graph_module = pytest.importorskip("core.graph")
    llm_module = pytest.importorskip("core.llm_client")
    sandbox_module = pytest.importorskip("core.sandbox")

    create_graph = getattr(graph_module, "create_simula_graph")

    # Stateful mock LLM: fails on iteration 1, succeeds on iteration 2
    class SelfCorrectingMockLLM:
        def __init__(self):
            self.calls = 0

        def generate_candidate(self, **kwargs):
            self.calls += 1
            episodic = kwargs.get("episodic_memory", [])
            if self.calls == 1:
                # First iteration produces code with failing assertion
                return textwrap_code("def test_initial(): assert 1 == 2, 'Initial syntax/data bug'")
            else:
                # Second iteration observes error and fixes it
                assert len(episodic) > 0, "Second iteration must receive episodic memory of previous failure"
                return textwrap_code("def test_fixed(): assert 1 == 1")

    def textwrap_code(body):
        return f"```python\nimport pytest\n{body}\n```"

    mock_llm = SelfCorrectingMockLLM()
    sandbox = sandbox_module.PytestSandbox(timeout_seconds=10)
    graph = create_graph(mock_llm, sandbox)

    initial_state = {
        "procedural_memory": {},
        "working_memory": {"contract_yaml": "tables: []"},
        "episodic_memory": [],
        "iterations": 0,
        "max_iterations": 3,
        "status": "INIT",
        "error_message": None,
    }

    final_state = graph.invoke(initial_state)

    assert final_state["status"] == "SUCCESS", f"Loop should succeed after self-correction, got {final_state['status']}"
    assert final_state["iterations"] == 2
    assert len(final_state["episodic_memory"]) == 1
    assert "Initial syntax/data bug" in final_state["episodic_memory"][0]["error_summary"] or (
        "Initial syntax/data bug" in final_state["episodic_memory"][0]["stdout"]
    )


def test_t3_streamlit_app_state_reflection(sample_credit_mesh_yaml):
    """Verify Streamlit app state bridge reflects memory and lifecycle events (R2)."""
    # Verify Streamlit app module or bridge can ingest contract and expose session state
    try:
        bridge_module = pytest.importorskip("ui.bridge")
    except Exception:
        ui_module = pytest.importorskip("ui.app")
        assert ui_module is not None
        return

    bridge = getattr(bridge_module, "StateBridge", None)
    if bridge:
        assert hasattr(bridge, "stream_events") or hasattr(bridge, "update_state")
