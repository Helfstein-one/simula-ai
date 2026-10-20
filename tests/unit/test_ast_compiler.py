"""tests/unit/test_ast_compiler.py - Unit tests for Hybrid Deterministic AST Compiler & Surgical Business Rules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from adapters.outbound.pytest_sandbox_adapter import PytestSandboxAdapter
from adapters.outbound.yaml_contract_adapter import YamlContractAdapter
from application.use_cases.simulate_mesh import SimulateMeshUseCase
from application.use_cases.synthesize_rules import SynthesizeBusinessRulesUseCase
from domain.ast_compiler import DomainASTCompiler
from domain.ast_validator import DomainASTValidator
from domain.entities import DataContract
from infrastructure.container import SimulaContainer


SAMPLE_CREDIT_CONTRACT = """
data_contract_version: "1.0.0"
version: "1.0.0"
dataset_name: "credit_mesh_ecosystem"
mesh_name: "credit_mesh_ecosystem"
description: "Corporate credit risk mesh"
tables:
  - name: "empresas"
    primary_key: "empresa_id"
    fields:
      - name: "empresa_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "cnpj"
        type: "string"
        faker: "cnpj"
        constraints:
          nullable: false
          regex: "^\\\\d{2}\\\\.\\\\d{3}\\\\.\\\\d{3}/\\\\d{4}-\\\\d{2}$"
      - name: "razao_social"
        type: "string"
        faker: "company"
        constraints:
          nullable: false
      - name: "faturamento_anual"
        type: "decimal"
        constraints:
          min: 100000.00
          max: 50000000.00
          nullable: false
  - name: "propostas"
    primary_key: "proposta_id"
    foreign_keys:
      - field: "empresa_id"
        references_table: "empresas"
        references_field: "empresa_id"
        relationship_type: "many_to_one"
    fields:
      - name: "proposta_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "empresa_id"
        type: "string"
        constraints:
          foreign_key: "empresas.empresa_id"
          nullable: false
      - name: "valor_solicitado"
        type: "decimal"
        constraints:
          min: 10000.00
          max: 1000000.00
          nullable: false
      - name: "status"
        type: "string"
        constraints:
          enum: ["APROVADA", "ANALISE", "RECUSADA"]
          nullable: false
  - name: "operacoes"
    primary_key: "operacao_id"
    foreign_keys:
      - field: "proposta_id"
        references_table: "propostas"
        references_field: "proposta_id"
        relationship_type: "one_to_one"
      - field: "empresa_id"
        references_table: "empresas"
        references_field: "empresa_id"
        relationship_type: "many_to_one"
    fields:
      - name: "operacao_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "proposta_id"
        type: "string"
        constraints:
          foreign_key: "propostas.proposta_id"
          nullable: false
      - name: "empresa_id"
        type: "string"
        constraints:
          foreign_key: "empresas.empresa_id"
          nullable: false
      - name: "valor_contratado"
        type: "decimal"
        constraints:
          min: 5000.00
          max: 1000000.00
          nullable: false
      - name: "codigo_contrato"
        type: "string"
        constraints:
          regex: "^OP-2026-\\\\d{6}$"
          nullable: false

business_rules:
  - id: "BR01_APROVACAO_OBRIGATORIA"
    description: "Operacoes devem referenciar propostas aprovadas"
    rule: "operacoes.valor_contratado <= propostas.valor_solicitado"
"""


class TestDomainASTCompiler:
    """Verifies deterministic Python code generation and 100% referential integrity."""

    @pytest.fixture
    def contract(self) -> DataContract:
        parser = YamlContractAdapter()
        return parser.parse(SAMPLE_CREDIT_CONTRACT)

    def test_compile_generator_syntax_validity(self, contract: DataContract):
        code = DomainASTCompiler.compile_generator_code(contract)
        assert isinstance(code, str)
        assert "def generate_mock_data" in code
        assert "empresas" in code
        assert "propostas" in code
        assert "operacoes" in code

        # Validate pure Python AST parse
        valid, err = DomainASTValidator.validate_syntax(code)
        assert valid is True, f"Syntax error: {err}"

    def test_compile_test_suite_syntax_validity(self, contract: DataContract):
        test_code = DomainASTCompiler.compile_test_suite_code(contract)
        assert "def test_tables_present" in test_code
        assert "def test_primary_key_uniqueness" in test_code
        assert "def test_foreign_key_referential_integrity" in test_code
        assert "def test_field_constraints" in test_code

        valid, err = DomainASTValidator.validate_syntax(test_code)
        assert valid is True, f"Syntax error in tests: {err}"

    def test_compiled_full_module_executes_successfully_in_sandbox(self, contract: DataContract):
        """Proves that compiled code runs in the Pytest sandbox and passes on iteration 1."""
        full_code = DomainASTCompiler.compile_full_module(contract)

        # In-memory structural validation
        report = DomainASTValidator.analyze_structure(full_code)
        assert report.is_valid is True
        assert report.has_generator is True
        assert report.has_tests is True

        # Sandbox execution
        sandbox = PytestSandboxAdapter(timeout_seconds=20)
        result = sandbox.execute(full_code)

        assert result.exit_code == 0, f"Pytest failed:\n{result.stderr}\n{result.stdout}"
        assert result.is_success is True

    def test_synthesize_business_rules_use_case(self, contract: DataContract):
        llm = SimulaContainer.get_llm_provider(mock_mode=True)
        uc = SynthesizeBusinessRulesUseCase(llm_provider=llm)
        snippets = uc.execute(contract)
        assert isinstance(snippets, dict)

    def test_simulate_mesh_use_case_with_hybrid_mode(self, contract: DataContract):
        simulate_uc = SimulaContainer.get_simulate_mesh_use_case(mock_mode=True)
        final_state = simulate_uc.execute(
            contract_source=contract,
            max_iterations=2,
            hybrid_mode=True,
        )

        assert final_state.get("status") == "SUCCESS"
        assert final_state.get("iterations") == 1
        assert final_state.get("working_memory", {}).get("pytest_exit_code") == 0
