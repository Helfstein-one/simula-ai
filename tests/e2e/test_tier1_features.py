"""Tier 1: Core Feature Verification Suite (R1 to R5).

Covers primary behavior (happy paths) for:
- R1: SimulaState, CoALA memory, regex think stripping, AST validation, subprocess sandbox, LangGraph loop.
- R2: Typer/Rich CLI commands, flags, help, and Streamlit app structure.
- R3: Mermaid ER deterministic extraction, type sanitization, file persistence.
- R4: Standalone generator export, test_mock.py export, and multi-format datasets.
- R5: Credit mesh contract YAML loading, Pydantic validation, packaging, and Containerfile.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

import pytest
try:
    from typer.testing import CliRunner
except ImportError:
    CliRunner = None


# ============================================================================
# R1: Cognitive Loop & State Management (CoALA Pattern)
# ============================================================================


def test_r1_simula_state_schema():
    """Verify SimulaState TypedDict contains all CoALA memory components (R1)."""
    state_module = pytest.importorskip("core.state")
    SimulaState = getattr(state_module, "SimulaState", None)
    assert SimulaState is not None, "SimulaState TypedDict must be defined in core.state"

    # Verify type annotations
    annotations = getattr(SimulaState, "__annotations__", {})
    required_keys = {
        "procedural_memory",
        "working_memory",
        "episodic_memory",
        "iterations",
        "status",
    }
    missing = required_keys - set(annotations.keys())
    assert not missing, f"SimulaState missing required CoALA keys: {missing}"


def test_r1_coala_procedural_memory_initialization():
    """Verify procedural memory contains guidelines for data engineering and testing (R1)."""
    memory_module = pytest.importorskip("core.memory")
    create_procedural = getattr(memory_module, "create_initial_procedural_memory", None)
    assert callable(create_procedural), "create_initial_procedural_memory must be defined in core.memory"

    procedural = create_procedural()
    assert isinstance(procedural, dict), "Procedural memory must return a dict"
    # Must contain guidelines for faker, topological ordering, pytest assertions
    keys = set(procedural.keys())
    assert any(k in keys for k in ["faker_rules", "relational_rules", "pytest_rules", "guidelines", "rules"]), (
        f"Procedural memory should contain domain engineering rules, got keys: {keys}"
    )


def test_r1_episodic_memory_record_structure():
    """Verify EpisodicMemoryRecord schema captures iterative tracebacks and metrics (R1)."""
    state_module = pytest.importorskip("core.state")
    RecordCls = getattr(state_module, "EpisodicMemoryRecord", None)
    assert RecordCls is not None, "EpisodicMemoryRecord must be defined in core.state"
    annotations = getattr(RecordCls, "__annotations__", {})
    expected = {"iteration", "exit_code", "stdout", "stderr"}
    missing = expected - set(annotations.keys())
    assert not missing, f"EpisodicMemoryRecord missing keys: {missing}"


def test_r1_openrouter_llm_client_configuration():
    """Verify OpenRouter LLM client sets up endpoints, models, and fallback mechanisms (R1)."""
    llm_module = pytest.importorskip("core.llm_client")
    OpenRouterClient = getattr(llm_module, "OpenRouterClient", None)
    assert OpenRouterClient is not None, "OpenRouterClient must be defined in core.llm_client"

    client = OpenRouterClient(api_key="test_key_dummy", base_url="https://openrouter.ai/api/v1")
    assert "openrouter.ai" in client.base_url
    assert hasattr(client, "primary_model") or hasattr(client, "model")


def test_r1_mock_llm_provider_offline_mode():
    """Verify Mock LLM provider returns deterministic Python code without network calls (R1)."""
    llm_module = pytest.importorskip("core.llm_client")
    MockClient = getattr(llm_module, "MockLLMClient", None)
    if MockClient is None:
        OpenRouterClient = getattr(llm_module, "OpenRouterClient", None)
        assert OpenRouterClient is not None
        client = OpenRouterClient(mock_mode=True)
    else:
        client = MockClient()

    output = client.generate_candidate(
        procedural_memory={},
        working_memory={"contract_yaml": "tables: []"},
        episodic_memory=[],
        iteration=1,
    )
    assert isinstance(output, str)
    assert "```python" in output or "import " in output, "Mock LLM output must contain Python candidate code"


def test_r1_regex_think_tag_stripping(sample_deepseek_r1_response):
    """Verify regex correctly strips <think>...</think> tags from DeepSeek R1 responses (R1 Acceptance)."""
    parser_module = pytest.importorskip("core.code_parser")
    CodeParser = getattr(parser_module, "CodeParser", None)
    assert CodeParser is not None, "CodeParser must be defined in core.code_parser"

    cleaned = CodeParser.strip_think_tags(sample_deepseek_r1_response)
    assert "<think>" not in cleaned.lower()
    assert "</think>" not in cleaned.lower()
    assert "I will create tables empresas" not in cleaned
    assert "```python" in cleaned


def test_r1_ast_code_extraction_and_syntax_validation(sample_deepseek_r1_response):
    """Verify extraction of python blocks and AST syntax validation (R1)."""
    parser_module = pytest.importorskip("core.code_parser")
    CodeParser = getattr(parser_module, "CodeParser", None)
    assert CodeParser is not None

    extracted = CodeParser.extract_python_code(sample_deepseek_r1_response)
    assert "def test_mesh_success():" in extracted
    assert "<think>" not in extracted

    valid, err = CodeParser.validate_syntax(extracted)
    assert valid is True
    assert err is None


def test_r1_subprocess_sandbox_isolated_execution(synthetic_valid_code):
    """Verify isolated subprocess Pytest execution with return code 0 and zero eval (R1 Acceptance)."""
    sandbox_module = pytest.importorskip("core.sandbox")
    PytestSandbox = getattr(sandbox_module, "PytestSandbox", None)
    assert PytestSandbox is not None, "PytestSandbox must be defined in core.sandbox"

    sandbox = PytestSandbox(timeout_seconds=20)
    result = sandbox.execute(synthetic_valid_code)

    assert result.exit_code == 0, f"Pytest sandbox should succeed with exit code 0. Stderr: {result.stderr}"
    assert result.is_success is True
    assert result.timed_out is False
    assert "passed" in result.stdout.lower() or result.exit_code == 0


def test_r1_langgraph_stategraph_initialization():
    """Verify LangGraph StateGraph builder initializes with required nodes and edges (R1)."""
    graph_module = pytest.importorskip("core.graph")
    create_graph = getattr(graph_module, "create_simula_graph", None)
    assert callable(create_graph), "create_simula_graph must be defined in core.graph"

    llm_module = pytest.importorskip("core.llm_client")
    sandbox_module = pytest.importorskip("core.sandbox")
    MockClient = getattr(llm_module, "MockLLMClient", None)
    client = MockClient() if MockClient else getattr(llm_module, "OpenRouterClient")(mock_mode=True)
    sandbox = getattr(sandbox_module, "PytestSandbox")()

    compiled_graph = create_graph(client, sandbox)
    assert compiled_graph is not None


# ============================================================================
# R2: Dual Interface (Typer CLI & Streamlit UI)
# ============================================================================


def test_r2_cli_typer_app_commands_and_help():
    """Verify interactive CLI Typer app provides required commands and flags (R2)."""
    cli_module = pytest.importorskip("cli.main")
    if CliRunner is None:
        pytest.importorskip("typer.testing")
    app = getattr(cli_module, "app", None)
    assert app is not None, "Typer app must be defined in cli.main"

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    help_text = result.stdout.lower()
    for cmd in ["run", "inspect", "diagram", "export", "test"]:
        assert cmd in help_text, f"Command '{cmd}' not found in CLI --help output"


def test_r2_cli_inspect_command_exists():
    """Verify CLI inspect command accepts contract path and displays info (R2)."""
    cli_module = pytest.importorskip("cli.main")
    if CliRunner is None:
        pytest.importorskip("typer.testing")
    app = getattr(cli_module, "app", None)
    runner = CliRunner()
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    assert "contract" in result.stdout.lower()



def test_r2_streamlit_ui_structure(project_root):
    """Verify Streamlit Web UI script exists and defines multi-tab layout (R2)."""
    ui_script = project_root / "ui" / "app.py"
    if not ui_script.exists():
        pytest.skip("ui/app.py not yet implemented")

    content = ui_script.read_text(encoding="utf-8")
    assert "streamlit" in content
    # Check tabs or structure
    assert "session_state" in content or "st." in content


# ============================================================================
# R3: Hybrid Mermaid ER Diagram Generation
# ============================================================================


def test_r3_mermaid_er_deterministic_extraction(sample_credit_mesh_yaml):
    """Verify deterministic Mermaid erDiagram syntax generation from schema (R3)."""
    diagram_module = pytest.importorskip("core.diagram")
    contract_module = pytest.importorskip("core.contract_parser")

    parse_contract = getattr(contract_module, "parse_contract")
    contract = parse_contract(sample_credit_mesh_yaml)

    generate_mermaid = getattr(diagram_module, "generate_mermaid_er")
    mmd = generate_mermaid(contract)

    assert isinstance(mmd, str)
    assert "erDiagram" in mmd
    assert "empresas" in mmd.lower()
    assert "propostas" in mmd.lower()
    assert "garantias" in mmd.lower()
    assert "operacoes" in mmd.lower()
    # Check relationships exist
    assert "--" in mmd


def test_r3_mermaid_type_sanitization():
    """Verify type sanitization removes parentheses and invalid chars for Mermaid compliance (R3)."""
    diagram_module = pytest.importorskip("core.diagram")
    GeneratorCls = getattr(diagram_module, "MermaidERGenerator", None)
    if GeneratorCls and hasattr(GeneratorCls, "sanitize_type"):
        assert GeneratorCls.sanitize_type("varchar(255)") == "varchar"
        assert GeneratorCls.sanitize_type("decimal(10,2)") == "decimal"
        assert GeneratorCls.sanitize_type("int") == "int"


def test_r3_mermaid_file_persistence(sample_credit_mesh_yaml, tmp_workspace):
    """Verify saving Mermaid ER diagram to output file (R3)."""
    diagram_module = pytest.importorskip("core.diagram")
    contract_module = pytest.importorskip("core.contract_parser")

    parse_contract = getattr(contract_module, "parse_contract")
    contract = parse_contract(sample_credit_mesh_yaml)

    generate_mermaid = getattr(diagram_module, "generate_mermaid_er")
    mmd = generate_mermaid(contract)

    output_file = tmp_workspace / "mesh_er_diagram.mmd"
    output_file.write_text(mmd, encoding="utf-8")
    assert output_file.exists()
    assert "erDiagram" in output_file.read_text(encoding="utf-8")


# ============================================================================
# R4: Standalone Deliverables & Multi-Format Data Export
# ============================================================================


def test_r4_deliverables_exporter_creates_files(sample_credit_mesh_yaml, synthetic_valid_code, tmp_workspace):
    """Verify export_deliverables generates generator.py, test_mock.py, and dataset files (R4)."""
    exporter_module = pytest.importorskip("core.exporter")
    contract_module = pytest.importorskip("core.contract_parser")

    export_fn = getattr(exporter_module, "export_deliverables", None)
    assert callable(export_fn), "export_deliverables must be defined in core.exporter"

    contract = contract_module.parse_contract(sample_credit_mesh_yaml)
    result_paths = export_fn(
        generated_code=synthetic_valid_code,
        output_dir=tmp_workspace,
        contract=contract,
        generate_datasets=True,
        rows=10,
        formats=["csv", "json", "parquet"],
    )

    assert isinstance(result_paths, dict)
    generator_path = tmp_workspace / "generator.py"
    test_path = tmp_workspace / "test_mock.py"
    assert generator_path.exists(), "output/generator.py must be exported"
    assert test_path.exists(), "output/test_mock.py must be exported"


# ============================================================================
# R5: Contract Ingestion & Podman Containerization
# ============================================================================


def test_r5_sample_credit_mesh_contract_yaml(project_root):
    """Verify contracts/exemplo_credito_mesh.yaml exists and parses with 4 tables (R5)."""
    contract_file = project_root / "contracts" / "exemplo_credito_mesh.yaml"
    if not contract_file.exists():
        pytest.skip("contracts/exemplo_credito_mesh.yaml not yet created")

    contract_module = pytest.importorskip("core.contract_parser")
    parse_contract = getattr(contract_module, "parse_contract")
    contract = parse_contract(str(contract_file))

    table_names = [t.name.lower() for t in contract.tables] if hasattr(contract, "tables") else []
    for expected in ["empresas", "propostas", "garantias", "operacoes"]:
        assert expected in table_names, f"Table '{expected}' missing from sample contract"


def test_r5_containerfile_rootless_specification(project_root):
    """Verify Containerfile exists and conforms to rootless container requirements (R5)."""
    containerfile = project_root / "Containerfile"
    if not containerfile.exists():
        pytest.skip("Containerfile not yet created")

    content = containerfile.read_text(encoding="utf-8")
    assert "FROM" in content
    assert "python" in content.lower()
    # Check non-root user configuration
    assert "USER" in content or "10001" in content or "simula" in content, (
        "Containerfile must specify non-root user for rootless Podman execution"
    )
    # Check port 8501 exposure for Streamlit
    assert "8501" in content, "Containerfile should expose port 8501 for Streamlit"


def test_r5_container_entrypoint_script(project_root):
    """Verify entrypoint.sh exists and supports cli/ui execution modes (R5)."""
    entrypoint = project_root / "entrypoint.sh"
    if not entrypoint.exists():
        pytest.skip("entrypoint.sh not yet created")

    content = entrypoint.read_text(encoding="utf-8")
    assert "#!/bin/" in content
    assert "streamlit" in content
    assert "cli" in content or "python" in content


def test_r5_packaging_and_documentation(project_root):
    """Verify pyproject.toml, requirements.txt, .env.example, and README.md exist (R5)."""
    pyproject = project_root / "pyproject.toml"
    requirements = project_root / "requirements.txt"
    env_example = project_root / ".env.example"
    readme = project_root / "README.md"

    for f in [pyproject, requirements, env_example, readme]:
        if not f.exists():
            pytest.skip(f"{f.name} not yet created")
        assert f.stat().st_size > 0, f"{f.name} must not be empty"
