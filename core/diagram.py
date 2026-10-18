"""core/diagram.py - Hybrid Mermaid ER Diagram Generator for Data Mesh contracts.

Generates standard Mermaid erDiagram representations with:
- Deterministic extraction from table schemas, column data types, PK/FK flags.
- Type sanitization removing parentheses (e.g. varchar(255) -> varchar, decimal(10,2) -> decimal).
- Relational edges (||--o{, ||--||, etc.) and relationship labels.
- Semantic annotations and business rule comments.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.contract_parser import DataContract, parse_contract


class MermaidERGenerator:
    """Generates Mermaid erDiagram representations from DataContract instances."""

    @staticmethod
    def sanitize_type(type_str: str) -> str:
        """Strip parameters like (255) or (10,2) and illegal characters for Mermaid syntax."""
        if not type_str:
            return "string"
        cleaned = re.sub(r"\(.*?\)", "", str(type_str).strip())
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", cleaned)
        cleaned = cleaned.strip("_")
        return cleaned.lower() or "string"

    @classmethod
    def generate(
        cls,
        contract: DataContract | dict[str, Any] | str,
        include_annotations: bool = True,
    ) -> str:
        """Builds a complete Mermaid erDiagram string from a DataContract."""
        if isinstance(contract, str):
            contract_obj = parse_contract(contract)
        elif isinstance(contract, dict):
            contract_obj = parse_contract(contract)
        else:
            contract_obj = contract

        lines: list[str] = ["erDiagram"]

        # 1. Generate Table Entities
        for table in contract_obj.tables:
            table_name = table.name.upper()
            lines.append(f"    {table_name} {{")
            for field in table.fields:
                field_type = cls.sanitize_type(field.type)
                field_name = field.name
                tags: list[str] = []
                if getattr(field, "primary_key", False):
                    tags.append("PK")
                if getattr(field, "foreign_key", None):
                    tags.append("FK")
                if getattr(field, "unique", False) and "PK" not in tags:
                    tags.append("UK")

                tag_suffix = f" {','.join(tags)}" if tags else ""
                comment = ""
                if include_annotations and getattr(field, "description", None):
                    # sanitize comment
                    desc = str(field.description).replace('"', "'").strip()
                    if desc:
                        comment = f' "{desc}"'
                lines.append(f"        {field_type} {field_name}{tag_suffix}{comment}")
            lines.append("    }")

        # 2. Generate Relational Edges
        # Check explicit relationships or infer from foreign keys
        relationships = []
        if hasattr(contract_obj, "get_relationships"):
            relationships = contract_obj.get_relationships()

        rendered_edges = set()
        for rel in relationships:
            parent = rel.parent_table.upper()
            child = rel.child_table.upper()
            symbol = rel.cardinality_symbol or "||--o{"
            if "--" not in symbol:
                symbol = "||--o{"
            label = rel.label or "references"
            edge_key = f"{parent}-{child}-{rel.child_field}"
            if edge_key not in rendered_edges:
                rendered_edges.add(edge_key)
                lines.append(f'    {parent} {symbol} {child} : "{label}"')

        # Fallback FK scan if no relationships list was extracted
        if not relationships:
            for table in contract_obj.tables:
                child = table.name.upper()
                for fk in getattr(table, "foreign_keys", []):
                    parent = fk.references_table.upper()
                    symbol = getattr(fk, "cardinality", None) or "||--o{"
                    if "--" not in symbol:
                        symbol = "||--o{"
                    label = getattr(fk, "relationship_name", None) or "possui"
                    lines.append(f'    {parent} {symbol} {child} : "{label}"')

        return "\n".join(lines) + "\n"


def generate_mermaid_er(
    contract: DataContract | dict[str, Any] | str,
    include_annotations: bool = True,
) -> str:
    """Convenience functional wrapper around MermaidERGenerator."""
    return MermaidERGenerator.generate(contract, include_annotations=include_annotations)


def save_mermaid_er(
    contract: DataContract | dict[str, Any] | str,
    output_path: Path | str,
) -> Path:
    """Generates Mermaid ER and writes it to disk."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    content = generate_mermaid_er(contract)
    out_file.write_text(content, encoding="utf-8")
    return out_file
