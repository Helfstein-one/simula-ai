"""adapters/outbound/pandas_exporter_adapter.py - Adapter for multi-format dataset and deliverable exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from application.ports.exporter_port import DatasetExporterPort
from core.exporter import export_deliverables
from domain.entities import DataContract


class PandasExporterAdapter(DatasetExporterPort):
    """Adapter implementing DatasetExporterPort via core export_deliverables."""

    def export(
        self,
        generated_code: str = "",
        output_dir: Path | str = ".",
        contract: Optional[DataContract] = None,
        generate_datasets: bool = True,
        rows: int = 10,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Exports generator.py, test_mock.py, and multi-format datasets."""
        return export_deliverables(
            generated_code=generated_code,
            output_dir=output_dir,
            contract=contract,
            generate_datasets=generate_datasets,
            rows=rows,
            formats=formats,
        )
