"""application/use_cases/inspect_contract.py - Use Case for inspecting contract schema and DAG."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from application.ports.contract_port import ContractParserPort
from domain.entities import DataContract, TableContract


@dataclass
class TableInspectionSummary:
    name: str
    column_count: int
    primary_key: str
    foreign_keys: List[str]


@dataclass
class ContractInspectionResult:
    contract: DataContract
    name: str
    version: str
    description: str
    topological_order: List[str]
    tables: List[TableInspectionSummary]


class InspectContractUseCase:
    """Use Case to inspect data contract schema, DAG dependencies, and constraints."""

    def __init__(self, parser: ContractParserPort) -> None:
        self.parser = parser

    def execute(self, source: str | Path | Dict[str, Any]) -> ContractInspectionResult:
        contract = self.parser.parse(source)
        dag_order = contract.topological_sort()

        table_summaries: List[TableInspectionSummary] = []
        for tbl in contract.tables:
            fks = [f"{fk.field}->{fk.references_table}.{fk.references_field}" for fk in getattr(tbl, "foreign_keys", [])]
            table_summaries.append(
                TableInspectionSummary(
                    name=tbl.name,
                    column_count=len(tbl.fields),
                    primary_key=tbl.primary_key if isinstance(tbl.primary_key, str) else ", ".join(tbl.primary_key),
                    foreign_keys=fks,
                )
            )

        return ContractInspectionResult(
            contract=contract,
            name=contract.name,
            version=contract.version,
            description=contract.description or "",
            topological_order=dag_order,
            tables=table_summaries,
        )
