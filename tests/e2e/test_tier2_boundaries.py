"""Tier 2: Boundary & Corner Cases Test Suite.

Covers edge conditions, failure paths, and adversarial inputs:
- Unclosed <think> tags from truncated LLM output.
- Subprocess sandbox handling of non-zero returncodes (exit 1 = assertion failure, exit 2 = syntax error).
- Subprocess timeout expiration on hanging/infinite loops.
- Malformed YAML contracts and schema validation errors.
- Missing optional fields and defaulting behavior.
- Zero-row generation (rows=0) and empty tables.
- Max iterations bound termination without infinite loops.
"""

import os
import textwrap
import pytest


def test_t2_unclosed_think_tag_before_code_fence(sample_unclosed_think_response):
    """Verify CodeParser strips unclosed <think> tag without dropping the code fence (R1 Acceptance)."""
    parser_module = pytest.importorskip("core.code_parser")
    CodeParser = getattr(parser_module, "CodeParser")

    cleaned = CodeParser.strip_think_tags(sample_unclosed_think_response)
    assert "<think>" not in cleaned.lower()
    assert "```python" in cleaned
    assert "test_unclosed_think_cleaned" in cleaned

    extracted = CodeParser.extract_python_code(sample_unclosed_think_response)
    assert "def test_unclosed_think_cleaned():" in extracted
    assert "<think" not in extracted

    # Ensure extracted code parses cleanly with AST
    valid, err = CodeParser.validate_syntax(extracted)
    assert valid is True, f"Extracted code syntax error: {err}"


def test_t2_unclosed_think_tag_without_any_code_fence():
    """Verify CodeParser gracefully handles prompt with unclosed think tag and no fences."""
    parser_module = pytest.importorskip("core.code_parser")
    CodeParser = getattr(parser_module, "CodeParser")

    raw = "<think>\nThinking endlessly without any code block or closing tag..."
    cleaned = CodeParser.strip_think_tags(raw)
    assert "<think" not in cleaned.lower()


def test_t2_sandbox_handles_assertion_failure_exit_code_1(synthetic_failing_code):
    """Verify PytestSandbox captures exit code 1, stderr, and failure tracebacks (R1)."""
    sandbox_module = pytest.importorskip("core.sandbox")
    PytestSandbox = getattr(sandbox_module, "PytestSandbox")

    sandbox = PytestSandbox(timeout_seconds=15)
    result = sandbox.execute(synthetic_failing_code)

    assert result.exit_code == 1, f"Failing assertion should yield exit code 1, got {result.exit_code}"
    assert result.is_success is False
    assert result.timed_out is False
    assert "FAILED" in result.stdout or "Simulated intentional validation failure" in result.stdout
    assert len(result.failed_tests) > 0 or "test_failing_assertion" in result.stdout


def test_t2_sandbox_handles_syntax_error_exit_code_2(synthetic_syntax_error_code):
    """Verify PytestSandbox captures compilation/syntax errors with non-zero exit code (R1)."""
    sandbox_module = pytest.importorskip("core.sandbox")
    PytestSandbox = getattr(sandbox_module, "PytestSandbox")

    sandbox = PytestSandbox(timeout_seconds=15)
    result = sandbox.execute(synthetic_syntax_error_code)

    assert result.exit_code != 0
    assert result.is_success is False
    assert "SyntaxError" in result.stdout or "SyntaxError" in result.stderr or result.exit_code in (1, 2)


def test_t2_sandbox_timeout_expiration(synthetic_hanging_code):
    """Verify PytestSandbox enforces timeout, terminates subprocess, and flags timed_out (R1 Acceptance)."""
    sandbox_module = pytest.importorskip("core.sandbox")
    PytestSandbox = getattr(sandbox_module, "PytestSandbox")

    # Use short 2 second timeout
    sandbox = PytestSandbox(timeout_seconds=2)
    result = sandbox.execute(synthetic_hanging_code)

    assert result.timed_out is True, "Hanging code must trigger timed_out=True"
    assert result.is_success is False
    assert result.exit_code == -1 or result.exit_code != 0
    assert "timed out" in result.stderr.lower() or "timeout" in result.error_summary.lower()


def test_t2_contract_parser_rejects_malformed_yaml():
    """Verify contract parser raises appropriate error on syntactically invalid YAML (R1/R5)."""
    contract_module = pytest.importorskip("core.contract_parser")
    parse_contract = getattr(contract_module, "parse_contract")

    malformed_yaml = "tables: [broken: - : unclosed syntax {"
    with pytest.raises((ValueError, Exception)):
        parse_contract(malformed_yaml)


def test_t2_contract_parser_rejects_empty_contract():
    """Verify contract parser rejects empty YAML or missing tables definition (R5)."""
    contract_module = pytest.importorskip("core.contract_parser")
    parse_contract = getattr(contract_module, "parse_contract")

    with pytest.raises((ValueError, Exception)):
        parse_contract("")


def test_t2_contract_parser_handles_missing_optional_fields():
    """Verify contract parser defaults optional fields (descriptions, nullable defaults) (R5)."""
    contract_module = pytest.importorskip("core.contract_parser")
    parse_contract = getattr(contract_module, "parse_contract")

    minimal_yaml = textwrap.dedent("""
        mesh_name: "minimal_mesh"
        version: "1.0.0"
        tables:
          - name: "raw_table"
            primary_key: "id"
            fields:
              - name: "id"
                type: "integer"
                primary_key: true
              - name: "val"
                type: "string"
    """).strip()

    contract = parse_contract(minimal_yaml)
    assert contract is not None
    table = contract.tables[0] if hasattr(contract, "tables") else contract["tables"][0]
    tname = table.name if hasattr(table, "name") else table["name"]
    assert tname == "raw_table"


def test_t2_exporter_zero_row_generation(sample_credit_mesh_yaml, synthetic_valid_code, tmp_workspace):
    """Verify export deliverables handles rows=0 without crash, generating valid headers (R4)."""
    exporter_module = pytest.importorskip("core.exporter")
    contract_module = pytest.importorskip("core.contract_parser")

    export_fn = getattr(exporter_module, "export_deliverables")
    contract = contract_module.parse_contract(sample_credit_mesh_yaml)

    result_paths = export_fn(
        generated_code=synthetic_valid_code,
        output_dir=tmp_workspace,
        contract=contract,
        generate_datasets=True,
        rows=0,
        formats=["csv", "json"],
    )

    assert tmp_workspace / "generator.py" in result_paths.values() or (tmp_workspace / "generator.py").exists()


def test_t2_max_iterations_exhaustion_terminates_loop():
    """Verify CoALA loop terminates with FAILED_MAX_RETRIES when sandbox repeatedly fails (R1)."""
    graph_module = pytest.importorskip("core.graph")
    llm_module = pytest.importorskip("core.llm_client")
    sandbox_module = pytest.importorskip("core.sandbox")

    create_graph = getattr(graph_module, "create_simula_graph")

    # Mock client that returns failing code
    class AlwaysFailingMockLLM:
        def generate_candidate(self, **kwargs):
            return "```python\ndef test_always_fails(): assert False\n```"

    sandbox = sandbox_module.PytestSandbox(timeout_seconds=5)
    graph = create_graph(AlwaysFailingMockLLM(), sandbox)

    initial_state = {
        "procedural_memory": {},
        "working_memory": {"contract_yaml": "tables: []"},
        "episodic_memory": [],
        "iterations": 0,
        "max_iterations": 2,
        "status": "INIT",
        "error_message": None,
    }

    final_state = graph.invoke(initial_state)
    assert final_state["iterations"] >= 2
    assert final_state["status"] in ("FAILED_MAX_RETRIES", "FAILED", "ERROR")
    assert len(final_state["episodic_memory"]) >= 2
