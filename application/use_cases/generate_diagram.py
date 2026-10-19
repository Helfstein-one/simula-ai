"""application/use_cases/generate_diagram.py - Use Case for generating Mermaid ER diagrams."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from application.ports.contract_port import ContractParserPort
from application.ports.diagram_port import DiagramGeneratorPort
from domain.entities import DataContract


class GenerateDiagramUseCase:
    """Use Case to synthesize Mermaid ER diagrams from Data Contracts."""

    def __init__(
        self,
        diagram_generator: DiagramGeneratorPort,
        contract_parser: ContractParserPort,
    ) -> None:
        self.diagram_generator = diagram_generator
        self.contract_parser = contract_parser

    def execute(
        self,
        contract_source: DataContract | str | Path | Dict[str, Any],
        output_path: Optional[Path | str] = None,
        include_annotations: bool = True,
    ) -> str:
        """Generates Mermaid erDiagram string, optionally saving to output_path."""
        if isinstance(contract_source, DataContract):
            contract = contract_source
        else:
            contract = self.contract_parser.parse(contract_source)

        diagram = self.diagram_generator.generate(
            contract=contract,
            include_annotations=include_annotations,
        )

        if output_path is not None:
            self.diagram_generator.save(contract=contract, output_path=output_path)

        return diagram
