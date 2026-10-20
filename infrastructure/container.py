"""infrastructure/container.py - Composition Root & Pure Python Dependency Injection Container.

Provides clean inversion of control (IoC) and wires hexagonal outbound adapters to
application use cases adhering strictly to SOLID principles without heavy third-party DI frameworks.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

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
from application.ports.sandbox_port import CodeSandboxPort
from application.ports.state_repository_port import StateRepositoryPort
from application.use_cases.export_deliverables import ExportDeliverablesUseCase
from application.use_cases.generate_diagram import GenerateDiagramUseCase
from application.use_cases.inspect_contract import InspectContractUseCase
from application.use_cases.simulate_mesh import SimulateMeshUseCase
from application.use_cases.synthesize_rules import SynthesizeBusinessRulesUseCase
from core.llm_client import DEFAULT_PRIMARY_MODEL


class SimulaContainer:
    """Composition root container providing factory methods for ports and use cases."""

    @staticmethod
    def get_contract_parser() -> ContractParserPort:
        """Returns standard YAML data contract parser adapter."""
        return YamlContractAdapter()

    @staticmethod
    def get_sandbox(
        sandbox_type: str = "auto",
        timeout_seconds: int = 30,
    ) -> CodeSandboxPort:
        """Returns isolated execution sandbox adapter (Podman with auto-fallback or pure Subprocess)."""
        if sandbox_type.lower() in ("podman", "auto"):
            return PodmanSandboxAdapter(timeout_seconds=timeout_seconds)
        return PytestSandboxAdapter(timeout_seconds=timeout_seconds)

    @staticmethod
    def get_state_repository(db_path: Optional[str | Path] = None) -> StateRepositoryPort:
        """Returns SQLite and JSONL state & memory persistence repository adapter."""
        return SqliteStateAdapter(db_path=db_path)

    @staticmethod
    def get_llm_provider(
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: bool = False,
        client: Any = None,
    ) -> LLMProviderPort:
        """Returns OpenRouter/Hermes LLM provider adapter or mock double."""
        return OpenRouterAdapter(
            model=model or DEFAULT_PRIMARY_MODEL,
            api_key=api_key,
            mock_mode=mock_mode,
            client=client,
        )

    @staticmethod
    def get_diagram_generator() -> DiagramGeneratorPort:
        """Returns Mermaid ER diagram generator adapter."""
        return MermaidDiagramAdapter()

    @staticmethod
    def get_dataset_exporter() -> DatasetExporterPort:
        """Returns multi-format dataset and deliverable exporter adapter."""
        return PandasExporterAdapter()

    @classmethod
    def get_inspect_contract_use_case(
        cls,
        parser: Optional[ContractParserPort] = None,
    ) -> InspectContractUseCase:
        """Assembles InspectContractUseCase with injected contract parser."""
        return InspectContractUseCase(parser=parser or cls.get_contract_parser())

    @classmethod
    def get_generate_diagram_use_case(
        cls,
        diagram_generator: Optional[DiagramGeneratorPort] = None,
        contract_parser: Optional[ContractParserPort] = None,
    ) -> GenerateDiagramUseCase:
        """Assembles GenerateDiagramUseCase with injected diagram and parser adapters."""
        return GenerateDiagramUseCase(
            diagram_generator=diagram_generator or cls.get_diagram_generator(),
            contract_parser=contract_parser or cls.get_contract_parser(),
        )

    @classmethod
    def get_export_deliverables_use_case(
        cls,
        exporter: Optional[DatasetExporterPort] = None,
    ) -> ExportDeliverablesUseCase:
        """Assembles ExportDeliverablesUseCase with injected dataset exporter."""
        return ExportDeliverablesUseCase(exporter=exporter or cls.get_dataset_exporter())

    @classmethod
    def get_synthesize_business_rules_use_case(
        cls,
        llm_provider: Optional[LLMProviderPort] = None,
    ) -> SynthesizeBusinessRulesUseCase:
        """Assembles SynthesizeBusinessRulesUseCase with injected LLM provider."""
        return SynthesizeBusinessRulesUseCase(llm_provider=llm_provider or cls.get_llm_provider())

    @classmethod
    def get_simulate_mesh_use_case(
        cls,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: bool = False,
        sandbox_timeout: int = 30,
        sandbox_type: str = "auto",
        client: Any = None,
        sandbox: Any = None,
        parser: Optional[ContractParserPort] = None,
        state_repository: Optional[StateRepositoryPort] = None,
    ) -> SimulateMeshUseCase:
        """Assembles SimulateMeshUseCase with injected LLM, Sandbox, Parser, and State Repository."""
        llm = client if isinstance(client, LLMProviderPort) else cls.get_llm_provider(
            model=model,
            api_key=api_key,
            mock_mode=mock_mode,
            client=client,
        )
        sb = sandbox if isinstance(sandbox, CodeSandboxPort) else (
            sandbox if hasattr(sandbox, "execute") and hasattr(sandbox, "is_success") else cls.get_sandbox(sandbox_type=sandbox_type, timeout_seconds=sandbox_timeout)
        )
        repo = state_repository if state_repository is not None else cls.get_state_repository()
        return SimulateMeshUseCase(
            llm_provider=llm,
            sandbox=sb,
            contract_parser=parser or cls.get_contract_parser(),
            state_repository=repo,
        )
