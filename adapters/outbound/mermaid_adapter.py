"""adapters/outbound/mermaid_adapter.py - Adapter for Mermaid ER diagram generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from application.ports.diagram_port import DiagramGeneratorPort
from core.diagram import MermaidERGenerator, save_mermaid_er
from domain.entities import DataContract


class MermaidDiagramAdapter(DiagramGeneratorPort):
    """Adapter for generating and persisting Mermaid ER diagrams."""

    def generate(
        self,
        contract: DataContract | str | Any,
        include_annotations: bool = True,
    ) -> str:
        """Renders Mermaid erDiagram syntax."""
        return MermaidERGenerator.generate(
            contract=contract,
            include_annotations=include_annotations,
        )

    def save(
        self,
        contract: DataContract | str | Any,
        output_path: Path | str,
    ) -> Path:
        """Renders diagram and writes it to disk."""
        return save_mermaid_er(contract=contract, output_path=output_path)
