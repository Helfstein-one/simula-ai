"""application/use_cases/synthesize_rules.py - Surgical AI Business Rules Synthesizer Use Case."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.ports.llm_port import LLMProviderPort
from domain.ast_validator import DomainASTValidator
from domain.entities import DataContract

logger = logging.getLogger("simula.use_cases.synthesize_rules")


class SynthesizeBusinessRulesUseCase:
    """Use Case coordinating surgical micro-synthesis of business rule functions using Hermes 3 AI."""

    def __init__(self, llm_provider: LLMProviderPort) -> None:
        self.llm_provider = llm_provider

    def execute(self, contract: DataContract) -> Dict[str, str]:
        """Synthesizes isolated pure Python functions for business rules declared in the contract."""
        rules = getattr(contract, "business_rules", []) or []
        if not rules:
            return {}

        snippets: Dict[str, str] = {}
        for r in rules:
            rule_id = getattr(r, "id", None) or getattr(r, "name", "BR")
            description = getattr(r, "description", "")
            rule_expr = getattr(r, "rule", "")

            # Generate micro-task prompt
            prompt = (
                f"You are synthesizing a single Python helper function for business rule: {rule_id}\n"
                f"Rule Description: {description}\n"
                f"Rule Expression: {rule_expr}\n"
                "Return ONLY a clean python function with this exact signature:\n"
                f"def apply_rule_{rule_id}(record: dict, parent_record: dict = None) -> dict:\n"
                "    # Modify and return record ensuring the rule constraint is satisfied\n"
                "    return record\n"
            )

            try:
                candidate = self.llm_provider.generate_candidate(
                    procedural_memory={"system_instruction": "Generate only valid Python function."},
                    working_memory={"prompt": prompt, "rule_id": rule_id},
                    iteration=1,
                )

                # Validate syntax in-memory
                valid, err = DomainASTValidator.validate_syntax(candidate)
                if valid:
                    snippets[rule_id] = candidate
                else:
                    logger.warning("Syntax validation failed for rule %s: %s. Skipping.", rule_id, err)
            except Exception as e:
                logger.warning("Failed to synthesize business rule %s: %s", rule_id, e)

        return snippets
