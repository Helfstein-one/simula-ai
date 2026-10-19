"""application/use_cases/export_deliverables.py - Use Case for exporting artifacts and datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from application.ports.exporter_port import DatasetExporterPort
from domain.entities import DataContract


class ExportDeliverablesUseCase:
    """Use Case to export generator code, Pytest suite, and multi-format datasets."""

    def __init__(self, exporter: DatasetExporterPort) -> None:
        self.exporter = exporter

    def execute(
        self,
        generated_code: str = "",
        output_dir: Path | str = ".",
        contract: Optional[DataContract] = None,
        generate_datasets: bool = True,
        rows: int = 10,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Executes the export pipeline and returns summary metadata."""
        return self.exporter.export(
            generated_code=generated_code,
            output_dir=output_dir,
            contract=contract,
            generate_datasets=generate_datasets,
            rows=rows,
            formats=formats,
        )
