"""domain/entities.py - Pure domain models, entities, and business constraints for Data Contracts."""

from __future__ import annotations

# Re-export pure domain models from contract_parser for clean hexagonal structure
from core.contract_parser import (
    BusinessRuleContract,
    CircularDependencyError,
    ContractError,
    ContractFileNotFoundError,
    ContractParseError,
    ContractValidationError,
    CyclicDependencyError,
    DataContract,
    DataContractError,
    DataContractValidationError,
    DuplicateFieldError,
    DuplicateTableError,
    FieldContract,
    ForeignKeyContract,
    ForeignKeyDefinition,
    InvalidForeignKeyError,
    MissingFieldError,
    MissingPrimaryKeyError,
    MissingTableError,
    RelationshipContract,
    TableContract,
)

TableSchema = TableContract
FieldSchema = FieldContract
CompositePrimaryKeyContract = TableContract
InvalidRelationshipError = InvalidForeignKeyError

__all__ = [
    "DataContract",
    "TableContract",
    "TableSchema",
    "FieldContract",
    "FieldSchema",
    "ForeignKeyDefinition",
    "ForeignKeyContract",
    "RelationshipContract",
    "BusinessRuleContract",
    "CompositePrimaryKeyContract",
    "DataContractError",
    "ContractError",
    "ContractFileNotFoundError",
    "ContractParseError",
    "DataContractValidationError",
    "ContractValidationError",
    "DuplicateTableError",
    "DuplicateFieldError",
    "InvalidForeignKeyError",
    "MissingTableError",
    "MissingFieldError",
    "MissingPrimaryKeyError",
    "CyclicDependencyError",
    "CircularDependencyError",
    "InvalidRelationshipError",
]
