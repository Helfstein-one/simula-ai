"""application/ports/diagram_port.py - Diagram Generator Port."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from domain.entities import DataContract


@runtime_checkable
class DiagramGeneratorPort(Protocol):
    """Port interface for rendering Entity-Relationship diagrams from contracts."""

    def generate(
        self,
        contract: DataContract | str | Any,
        include_annotations: bool = True,
    ) -> str:
        """Renders Mermaid erDiagram syntax."""
        ...

    def save(
        self,
        contract: DataContract | str | Any,
        output_path: Path | str,
    ) -> Path:
        """Renders diagram and writes it to a file."""
        ...
