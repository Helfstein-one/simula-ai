"""application/ports/contract_port.py - Data Contract Ingestion & Parser Port."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable

from domain.entities import DataContract


@runtime_checkable
class ContractParserPort(Protocol):
    """Port interface for reading, parsing, and validating data contracts."""

    def parse(self, raw_source: str | Path | Dict[str, Any]) -> DataContract:
        """Parses YAML text, file path, or dictionary into a validated DataContract."""
        ...
