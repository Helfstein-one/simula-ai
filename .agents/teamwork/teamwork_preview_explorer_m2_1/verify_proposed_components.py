"""Verification script for proposed core/state.py, core/memory.py, core/llm_client.py.

Validates that all proposed blueprints satisfy E2E tier requirements and CoALA specifications.
"""

import os
import sys
from pathlib import Path

# Add current folder and project root to sys.path
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

# Test imports
import proposed_state as state_mod
import proposed_memory as mem_mod
import proposed_llm_client as llm_mod


def test_state_schema():
    SimulaState = getattr(state_mod, "SimulaState")
    annotations = SimulaState.__annotations__
    required_keys = {
        "procedural_memory",
        "working_memory",
        "episodic_memory",
        "iterations",
        "status",
    }
    missing = required_keys - set(annotations.keys())
    assert not missing, f"SimulaState missing required keys: {missing}"

    EpisodicRecord = getattr(state_mod, "EpisodicMemoryRecord")
    rec_annotations = EpisodicRecord.__annotations__
    expected = {"iteration", "exit_code", "stdout", "stderr"}
    missing_rec = expected - set(rec_annotations.keys())
    assert not missing_rec, f"EpisodicMemoryRecord missing keys: {missing_rec}"
    print("[PASS] State Schema & Episodic Record Schema verified.")


def test_memory_procedural_initialization():
    create_fn = getattr(mem_mod, "create_initial_procedural_memory")
    procedural = create_fn()
    assert isinstance(procedural, dict)
    keys = set(procedural.keys())
    assert any(k in keys for k in ["faker_rules", "relational_rules", "pytest_rules", "guidelines", "rules"])
    assert len(procedural["faker_rules"]) >= 5
    assert len(procedural["relational_rules"]) >= 3
    assert len(procedural["pytest_rules"]) >= 5
    print("[PASS] Procedural Memory Initialization verified.")


def test_memory_episodic_parsing_and_feedback():
    sample_stdout = """
============================= test session starts ==============================
collected 3 items

simula_temp_test.py::test_empresas_count PASSED
simula_temp_test.py::test_propostas_fk FAILED
simula_temp_test.py::test_garantias PASSED

=================================== FAILURES ===================================
______________________________ test_propostas_fk _______________________________
    def test_propostas_fk():
>       assert prop['empresa_id'] in empresa_pks
E       AssertionError: Proposta FK missing in empresas
simula_temp_test.py:45: AssertionError
=========================== short test summary info ============================
FAILED simula_temp_test.py::test_propostas_fk - AssertionError: Proposta FK missing in empresas
"""
    rec = mem_mod.create_episodic_record(
        iteration=1,
        generated_code="code snippet",
        exit_code=1,
        stdout=sample_stdout,
        stderr="",
    )
    assert rec["iteration"] == 1
    assert rec["exit_code"] == 1
    assert "test_propostas_fk" in rec["failed_tests"]
    assert "Proposta FK missing in empresas" in rec["error_summary"]

    feedback = mem_mod.format_episodic_feedback([rec])
    assert "Attempt #1" in feedback
    assert "test_propostas_fk" in feedback
    assert "REPAIR DIRECTIVES" in feedback
    print("[PASS] Episodic Memory Traceback Parsing & Feedback Formatting verified.")


def test_llm_client_configuration():
    ClientCls = getattr(llm_mod, "OpenRouterClient")
    client = ClientCls(api_key="test_dummy_key", base_url="https://openrouter.ai/api/v1")
    assert "openrouter.ai" in client.base_url
    assert hasattr(client, "primary_model") or hasattr(client, "model")
    assert client.primary_model == "deepseek/deepseek-r1"
    assert "deepseek/deepseek-chat" in client.fallback_models
    print("[PASS] OpenRouter Client Configuration verified.")


def test_mock_llm_deterministic_output():
    MockCls = getattr(llm_mod, "MockLLMClient")
    mock_client = MockCls()
    out = mock_client.generate_candidate(
        procedural_memory={},
        working_memory={"contract_yaml": "tables: []"},
        episodic_memory=[],
        iteration=1,
    )
    assert isinstance(out, str)
    assert "```python" in out or "import " in out
    assert "def generate_mock_data" in out
    assert "def test_" in out
    print("[PASS] Mock LLM Deterministic Output verified.")


def test_mock_llm_iterative_retry_support():
    # Test retry mode where iteration 1 fails and iteration 2 passes
    MockCls = getattr(llm_mod, "MockLLMClient")
    mock_client = MockCls(fail_first_iteration=True)

    iter1_code = mock_client.generate_candidate(
        procedural_memory={},
        working_memory={"contract_yaml": "tables: []"},
        episodic_memory=[],
        iteration=1,
    )
    assert "test_intentional_mock_failure" in iter1_code
    assert "assert 1 == 2" in iter1_code

    # Create dummy episodic record simulating the failure
    failed_rec = mem_mod.create_episodic_record(
        iteration=1,
        generated_code=iter1_code,
        exit_code=1,
        stdout="FAILED test_intentional_mock_failure",
        stderr="",
        error_summary="Intentional mock validation failure",
        failed_tests=["test_intentional_mock_failure"],
    )

    iter2_code = mock_client.generate_candidate(
        procedural_memory={},
        working_memory={"contract_yaml": "tables: []"},
        episodic_memory=[failed_rec],
        iteration=2,
    )
    assert "test_intentional_mock_failure" not in iter2_code
    assert "assert 1 == 2" not in iter2_code
    assert "test_empresas_primary_key_uniqueness" in iter2_code
    print("[PASS] Mock LLM Iterative Retry Testing (Fail iter 1 -> Fix iter 2) verified.")


def test_openrouter_jitter_calculation():
    ClientCls = getattr(llm_mod, "OpenRouterClient")
    client = ClientCls(mock_mode=True)
    d0 = client._calculate_jitter_delay(attempt=0)
    d1 = client._calculate_jitter_delay(attempt=1)
    d2 = client._calculate_jitter_delay(attempt=2)
    assert 0.5 <= d0 <= 2.0
    assert 0.5 <= d1 <= 4.0
    assert 0.5 <= d2 <= 8.0

    # Retry-after respect
    d_ra = client._calculate_jitter_delay(attempt=0, retry_after=12.5)
    assert d_ra >= 12.5
    print("[PASS] OpenRouter Full Jitter & Retry-After calculation verified.")


if __name__ == "__main__":
    test_state_schema()
    test_memory_procedural_initialization()
    test_memory_episodic_parsing_and_feedback()
    test_llm_client_configuration()
    test_mock_llm_deterministic_output()
    test_mock_llm_iterative_retry_support()
    test_openrouter_jitter_calculation()
    print("\nALL 7 VERIFICATION TESTS PASSED SUCCESSFULLY!")
