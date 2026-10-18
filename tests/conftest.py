"""Shared fixtures and configuration for Simula-AI E2E test suites."""

import os
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Generator

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the absolute Path to the Simula-AI project root."""
    return PROJECT_ROOT


@pytest.fixture
def tmp_workspace() -> Generator[Path, None, None]:
    """Provide a temporary directory for sandbox / export artifacts."""
    with tempfile.TemporaryDirectory(prefix="simula_test_workspace_") as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_credit_mesh_yaml() -> str:
    """Canonical 4-table Brazilian corporate credit mesh YAML contract."""
    return textwrap.dedent("""
        mesh_name: "credit_mesh_ecosystem"
        version: "1.0.0"
        domain: "credit_risk"
        description: "Autonomous Brazilian corporate credit mesh scenario"
        tables:
          - name: "empresas"
            description: "Debtor corporate entities"
            primary_key: "empresa_id"
            fields:
              - name: "empresa_id"
                type: "string"
                primary_key: true
                nullable: false
                unique: true
              - name: "cnpj"
                type: "string"
                nullable: false
                unique: true
                rules: ["regex:^\\\\d{2}\\\\.\\\\d{3}\\\\.\\\\d{3}/\\\\d{4}-\\\\d{2}$"]
              - name: "razao_social"
                type: "string"
                nullable: false
              - name: "faturamento_anual"
                type: "decimal"
                nullable: false
              - name: "status_cadastral"
                type: "string"
                nullable: false
            business_rules:
              - "cnpj must be valid Brazilian company tax id"

          - name: "propostas"
            description: "Credit loan applications"
            primary_key: "proposta_id"
            fields:
              - name: "proposta_id"
                type: "string"
                primary_key: true
                nullable: false
                unique: true
              - name: "empresa_id"
                type: "string"
                nullable: false
                foreign_key: "empresas.empresa_id"
              - name: "data_solicitacao"
                type: "datetime"
                nullable: false
              - name: "valor_solicitado"
                type: "decimal"
                nullable: false
              - name: "status_proposta"
                type: "string"
                nullable: false
            business_rules:
              - "empresa_id must exist in empresas"

          - name: "garantias"
            description: "Collateral assets pledged for loan proposals"
            primary_key: "garantia_id"
            fields:
              - name: "garantia_id"
                type: "string"
                primary_key: true
                nullable: false
                unique: true
              - name: "proposta_id"
                type: "string"
                nullable: false
                foreign_key: "propostas.proposta_id"
              - name: "tipo_garantia"
                type: "string"
                nullable: false
              - name: "valor_avaliado"
                type: "decimal"
                nullable: false
            business_rules:
              - "proposta_id must exist in propostas"

          - name: "operacoes"
            description: "Executed and active credit contracts"
            primary_key: "operacao_id"
            fields:
              - name: "operacao_id"
                type: "string"
                primary_key: true
                nullable: false
                unique: true
              - name: "proposta_id"
                type: "string"
                nullable: false
                foreign_key: "propostas.proposta_id"
              - name: "data_contratacao"
                type: "datetime"
                nullable: false
              - name: "valor_contratado"
                type: "decimal"
                nullable: false
            business_rules:
              - "proposta_id must be in APROVADA status"
              - "valor_contratado must not exceed valor_solicitado"
    """).strip()


@pytest.fixture
def synthetic_valid_code() -> str:
    """Executable Python generator script with passing pytest assertions."""
    return textwrap.dedent("""
        import pytest
        import uuid

        def generate_mock_data():
            return {
                "empresas": [{"empresa_id": str(uuid.uuid4()), "razao_social": "Alpha Ltda"}],
                "propostas": [{"proposta_id": str(uuid.uuid4()), "valor": 50000.0}]
            }

        def test_empresas_not_empty():
            data = generate_mock_data()
            assert len(data["empresas"]) == 1
            assert "empresa_id" in data["empresas"][0]

        def test_propostas_not_empty():
            data = generate_mock_data()
            assert len(data["propostas"]) == 1
            assert data["propostas"][0]["valor"] > 0
    """).strip()


@pytest.fixture
def synthetic_failing_code() -> str:
    """Executable Python script with failing pytest assertion."""
    return textwrap.dedent("""
        import pytest

        def test_failing_assertion():
            assert 1 + 1 == 42, "Simulated intentional validation failure"
    """).strip()


@pytest.fixture
def synthetic_syntax_error_code() -> str:
    """Invalid Python script causing syntax error."""
    return "def broken_syntax(:\n    return False\n"


@pytest.fixture
def synthetic_hanging_code() -> str:
    """Hanging script to trigger sandbox timeout."""
    return textwrap.dedent("""
        import time

        def test_hanging_loop():
            start = time.time()
            while time.time() - start < 100:
                time.sleep(0.05)
            assert True
    """).strip()


@pytest.fixture
def sample_deepseek_r1_response() -> str:
    """Sample raw LLM response from DeepSeek R1 with closed think tags."""
    return textwrap.dedent("""
        <think>
        The user wants a mock generator for credit mesh.
        I will create tables empresas and propostas with topological sorting.
        First import faker and pytest.
        Then write test_propostas_fk.
        </think>
        Here is the implementation:
        ```python
        import pytest

        def test_mesh_success():
            assert True
        ```
    """).strip()


@pytest.fixture
def sample_unclosed_think_response() -> str:
    """Sample raw LLM response with unclosed <think> tag before markdown fence."""
    return textwrap.dedent("""
        <think>
        Here is my internal reasoning that was truncated before the tag closed...
        ```python
        import pytest

        def test_unclosed_think_cleaned():
            assert 10 > 5
        ```
    """).strip()
