"""domain/grounding.py - Domain template grounding generator for Hermes 3 AI."""

from __future__ import annotations

from typing import Any, Dict, List


class DomainTemplateGrounding:
    """Builds topologically ordered skeleton templates to maximize LLM generation assertiveness."""

    @classmethod
    def generate_scaffolding(cls, contract: Any) -> str:
        """Constructs code skeleton ordered by table dependencies."""
        if not hasattr(contract, "tables") or not contract.tables:
            return ""

        dag_order = contract.topological_sort() if hasattr(contract, "topological_sort") else [t.name for t in contract.tables]
        table_map = {t.name: t for t in contract.tables}

        scaffold_lines: List[str] = [
            "# TOPOLOGICAL INGESTION SCAFFOLDING (Order enforced by Kahn DAG)",
            "# Follow this exact generation sequence to guarantee 100% referential integrity:",
        ]

        for idx, tname in enumerate(dag_order, 1):
            table = table_map.get(tname)
            if not table:
                continue
            pk = getattr(table, "primary_key", "id")
            fks = [f"{fk.field} -> {fk.references_table}.{fk.references_field}" for fk in getattr(table, "foreign_keys", [])]
            fk_note = f" (Depends on: {', '.join(fks)})" if fks else " (Root / Parent Table)"
            scaffold_lines.append(f"# {idx}. {tname} [PK: {pk}]{fk_note}")

        return "\n".join(scaffold_lines)
