"""adapters/outbound/yaml_contract_adapter.py - Contract parser adapter for YAML files and dicts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from application.ports.contract_port import ContractParserPort
from core.contract_parser import parse_contract
from domain.entities import DataContract


class YamlContractAdapter(ContractParserPort):
    """Adapter implementing ContractParserPort using core contract parser."""

    def parse(self, raw_source: str | Path | Dict[str, Any]) -> DataContract:
        """Parses YAML text, file path, or dictionary into a validated DataContract."""
        return parse_contract(raw_source)
