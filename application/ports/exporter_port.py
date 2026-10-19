"""application/ports/exporter_port.py - Deliverables & Multi-Format Dataset Exporter Port."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from domain.entities import DataContract


@runtime_checkable
class DatasetExporterPort(Protocol):
    """Port interface for exporting standalone generator, tests, and mock datasets."""

    def export(
        self,
        generated_code: str = "",
        output_dir: Path | str = ".",
        contract: Optional[DataContract] = None,
        generate_datasets: bool = True,
        rows: int = 10,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Exports generator.py, test_mock.py, and datasets into the target directory."""
        ...
