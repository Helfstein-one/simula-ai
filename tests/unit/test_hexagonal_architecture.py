"""tests/unit/test_hexagonal_architecture.py - Unit tests for Hexagonal Ports, Adapters, & SOLID Use Cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from adapters.inbound.api.router import SimulaAPIRouter
from adapters.inbound.cli.controller import CLIController
from adapters.inbound.web.view_controller import WebViewController
from adapters.outbound.mermaid_adapter import MermaidDiagramAdapter
from adapters.outbound.openrouter_adapter import OpenRouterAdapter
from adapters.outbound.pandas_exporter_adapter import PandasExporterAdapter
from adapters.outbound.podman_sandbox_adapter import PodmanSandboxAdapter
from adapters.outbound.pytest_sandbox_adapter import PytestSandboxAdapter
from adapters.outbound.sqlite_state_adapter import SqliteStateAdapter
from adapters.outbound.yaml_contract_adapter import YamlContractAdapter
from application.ports.contract_port import ContractParserPort
from application.ports.diagram_port import DiagramGeneratorPort
from application.ports.exporter_port import DatasetExporterPort
from application.ports.llm_port import LLMProviderPort
from application.ports.sandbox_port import CodeSandboxPort, SandboxResult
from application.ports.state_repository_port import StateRepositoryPort
from application.use_cases.export_deliverables import ExportDeliverablesUseCase
from application.use_cases.generate_diagram import GenerateDiagramUseCase
from application.use_cases.inspect_contract import InspectContractUseCase
from application.use_cases.simulate_mesh import SimulateMeshUseCase
from domain.ast_validator import DomainASTValidator
from domain.entities import DataContract
from domain.grounding import DomainTemplateGrounding
from infrastructure.container import SimulaContainer


SAMPLE_VALID_YAML = """
data_contract_version: "1.0.0"
version: "1.0.0"
dataset_name: "test_mesh"
mesh_name: "test_mesh"
description: "Test Relational Mesh"
tables:
  - name: "parents"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
  - name: "children"
    primary_key: "cid"
    foreign_keys:
      - field: "parent_id"
        references_table: "parents"
        references_field: "id"
        relationship_type: "many_to_one"
    fields:
      - name: "cid"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "parent_id"
        type: "string"
        constraints:
          nullable: false
          foreign_key: "parents.id"
"""


class TestDomainComponents:
    """Verifies domain entities, validators, and template grounding."""

    def test_domain_ast_validator_detects_valid_code(self):
        valid_code = """
def generate_mock_data(rows: int = 10):
    return {"users": [{"id": i} for i in range(rows)]}

def test_mock_generation():
    data = generate_mock_data(5)
    assert len(data["users"]) == 5
"""
        report = DomainASTValidator.analyze_structure(valid_code)
        assert report.is_valid is True
        assert report.has_generator is True
        assert report.has_tests is True
        assert not report.security_violations

    def test_domain_ast_validator_detects_missing_generator(self):
        code_without_gen = """
def test_something():
    assert True
"""
        report = DomainASTValidator.analyze_structure(code_without_gen)
        assert report.is_valid is False
        assert "Missing mandatory function: `generate_mock_data(rows: int)`" in (report.error_message or "")

    def test_domain_ast_validator_detects_security_violations(self):
        malicious_code = """
def generate_mock_data(rows: int = 10):
    eval("1 + 1")
    return {}

def test_something():
    assert True
"""
        report = DomainASTValidator.analyze_structure(malicious_code)
        assert report.is_valid is False
        assert any("Forbidden built-in call: eval" in v for v in report.security_violations)

    def test_domain_template_grounding_orders_scaffolding(self):
        parser = YamlContractAdapter()
        contract = parser.parse(SAMPLE_VALID_YAML)
        scaffold = DomainTemplateGrounding.generate_scaffolding(contract)
        assert "parents" in scaffold
        assert "children" in scaffold
        # Parent must precede children
        assert scaffold.index("parents") < scaffold.index("children")


class TestPortProtocolsCompliance:
    """Verifies that all outbound adapters implement their port Protocols."""

    def test_adapters_satisfy_protocols(self):
        assert isinstance(YamlContractAdapter(), ContractParserPort)
        assert isinstance(PytestSandboxAdapter(), CodeSandboxPort)
        assert isinstance(OpenRouterAdapter(mock_mode=True), LLMProviderPort)
        assert isinstance(MermaidDiagramAdapter(), DiagramGeneratorPort)
        assert isinstance(PandasExporterAdapter(), DatasetExporterPort)


class TestUseCasesIsolationAndDIP:
    """Verifies use cases adhere to Dependency Inversion (DIP) and run with mocks."""

    def test_inspect_contract_use_case(self):
        mock_parser = MagicMock(spec=ContractParserPort)
        contract = YamlContractAdapter().parse(SAMPLE_VALID_YAML)
        mock_parser.parse.return_value = contract

        use_case = InspectContractUseCase(parser=mock_parser)
        result = use_case.execute(SAMPLE_VALID_YAML)

        assert result.name == "test_mesh"
        assert result.topological_order == ["parents", "children"]
        assert len(result.tables) == 2
        mock_parser.parse.assert_called_once()

    def test_generate_diagram_use_case(self):
        mock_diagram = MagicMock(spec=DiagramGeneratorPort)
        mock_parser = MagicMock(spec=ContractParserPort)
        mock_diagram.generate.return_value = "erDiagram\nPARENTS ||--o{ CHILDREN : has"

        use_case = GenerateDiagramUseCase(diagram_generator=mock_diagram, contract_parser=mock_parser)
        res = use_case.execute(contract_source=SAMPLE_VALID_YAML)

        assert "erDiagram" in res
        mock_diagram.generate.assert_called_once()

    def test_export_deliverables_use_case(self, tmp_path: Path):
        mock_exporter = MagicMock(spec=DatasetExporterPort)
        mock_exporter.export.return_value = {"generator": tmp_path / "generator.py", "datasets": []}

        use_case = ExportDeliverablesUseCase(exporter=mock_exporter)
        summary = use_case.execute(generated_code="# code", output_dir=tmp_path)

        assert "generator" in summary
        mock_exporter.export.assert_called_once()

    def test_simulate_mesh_use_case_in_mock_mode(self):
        llm = OpenRouterAdapter(mock_mode=True)
        sandbox = PytestSandboxAdapter(timeout_seconds=15)
        parser = YamlContractAdapter()

        use_case = SimulateMeshUseCase(llm_provider=llm, sandbox=sandbox, contract_parser=parser)
        final_state = use_case.execute(contract_source=SAMPLE_VALID_YAML, max_iterations=3)

        assert final_state.get("status") == "SUCCESS"
        assert final_state.get("working_memory", {}).get("pytest_exit_code") == 0


class TestSimulaContainerCompositionRoot:
    """Verifies SimulaContainer factory methods and dependency assembly."""

    def test_container_provides_ports(self):
        assert isinstance(SimulaContainer.get_contract_parser(), ContractParserPort)
        assert isinstance(SimulaContainer.get_sandbox(), CodeSandboxPort)
        assert isinstance(SimulaContainer.get_llm_provider(mock_mode=True), LLMProviderPort)
        assert isinstance(SimulaContainer.get_diagram_generator(), DiagramGeneratorPort)
        assert isinstance(SimulaContainer.get_dataset_exporter(), DatasetExporterPort)

    def test_container_assembles_use_cases(self):
        inspect_uc = SimulaContainer.get_inspect_contract_use_case()
        assert isinstance(inspect_uc, InspectContractUseCase)

        diagram_uc = SimulaContainer.get_generate_diagram_use_case()
        assert isinstance(diagram_uc, GenerateDiagramUseCase)

        export_uc = SimulaContainer.get_export_deliverables_use_case()
        assert isinstance(export_uc, ExportDeliverablesUseCase)

        simulate_uc = SimulaContainer.get_simulate_mesh_use_case(mock_mode=True)
        assert isinstance(simulate_uc, SimulateMeshUseCase)

        state_repo = SimulaContainer.get_state_repository()
        assert isinstance(state_repo, StateRepositoryPort)


class TestSqliteStatePersistence:
    """Verifies SQLite and JSONL persistence of CoALA session checkpoints."""

    def test_save_and_retrieve_checkpoints(self, tmp_path: Path):
        db_file = tmp_path / "test_simula.db"
        adapter = SqliteStateAdapter(db_path=db_file)
        assert isinstance(adapter, StateRepositoryPort)

        session_id = "test_sess_001"
        test_state = {
            "iterations": 1,
            "max_iterations": 3,
            "status": "INIT",
            "working_memory": {"contract_yaml": "mesh_name: test"},
            "episodic_memory": [],
        }

        adapter.save_checkpoint(session_id, 0, test_state, status="INIT", message="Starting")
        adapter.save_checkpoint(session_id, 1, test_state, status="SUCCESS", message="Finished")

        history = adapter.get_session_history(session_id)
        assert len(history) == 2
        assert history[0]["status"] == "INIT"
        assert history[1]["status"] == "SUCCESS"

        sessions = adapter.list_sessions()
        assert len(sessions) >= 1
        assert sessions[0]["session_id"] == session_id

        # Export to JSONL
        jsonl_path = tmp_path / "trace.jsonl"
        exported = adapter.export_session_jsonl(session_id, str(jsonl_path))
        assert Path(exported).exists()
        assert Path(exported).stat().st_size > 0


class TestPodmanSandboxFallback:
    """Verifies Podman sandbox protocol compliance and automatic fallback."""

    def test_podman_sandbox_satisfies_protocol(self):
        sandbox = PodmanSandboxAdapter(timeout_seconds=5)
        assert isinstance(sandbox, CodeSandboxPort)

    def test_podman_fallback_execution_on_valid_code(self):
        # Even without Podman running, fallback executes successfully
        sandbox = PodmanSandboxAdapter(timeout_seconds=15)
        code = """
def test_something():
    assert 2 + 2 == 4
"""
        result = sandbox.execute(code)
        assert isinstance(result, SandboxResult)
        assert result.is_success is True


class TestInboundDrivingAdapters:
    """Verifies CLIController, WebViewController, and SimulaAPIRouter driving adapters."""

    def test_cli_controller_inspect_and_diagram(self):
        controller = CLIController()
        summary = controller.inspect_contract(SAMPLE_VALID_YAML)
        assert summary.name == "test_mesh"

        diagram = controller.generate_diagram(SAMPLE_VALID_YAML)
        assert "erDiagram" in diagram

    def test_web_view_controller_run(self, tmp_path: Path):
        web = WebViewController()
        res = web.run_simulation(
            yaml_content=SAMPLE_VALID_YAML,
            mock_mode=True,
            output_dir=tmp_path,
        )
        assert res["final_state"]["status"] == "SUCCESS"
        assert res["artifacts"] is not None

    def test_api_router_endpoints(self):
        api = SimulaAPIRouter()
        inspect_data = api.inspect_contract(SAMPLE_VALID_YAML)
        assert inspect_data["name"] == "test_mesh"
        assert len(inspect_data["tables"]) == 2

        diagram_data = api.generate_diagram(SAMPLE_VALID_YAML)
        assert "erDiagram" in diagram_data["mermaid"]

        sim_data = api.run_simulation(SAMPLE_VALID_YAML, mock_mode=True)
        assert sim_data["status"] == "SUCCESS"
