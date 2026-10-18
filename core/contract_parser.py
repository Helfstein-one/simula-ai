"""Simula-AI Data Contract Parser & Validator.

Ingests YAML data contracts, validates multi-table relational schemas via Pydantic v2,
resolves table dependency DAGs using Kahn's topological sort, and validates referential integrity.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

# ==============================================================================
# Custom Exceptions Hierarchy
# ==============================================================================


class DataContractError(Exception):
    """Base exception for all data contract errors."""


# Backward-compatibility alias
ContractError = DataContractError


class ContractFileNotFoundError(DataContractError):
    """Raised when the specified contract YAML file does not exist."""


class ContractParseError(DataContractError):
    """Raised when YAML syntax is invalid or cannot be parsed."""


class DataContractValidationError(DataContractError):
    """Raised when contract content violates schema or relational rules."""


# Backward-compatibility alias
ContractValidationError = DataContractValidationError


class DuplicateTableError(DataContractValidationError):
    """Raised when duplicate table names are detected in the contract."""


class DuplicateFieldError(DataContractValidationError):
    """Raised when duplicate field names are detected within a table."""


class InvalidForeignKeyError(DataContractValidationError):
    """Raised when a foreign key format is invalid or references are malformed."""


class MissingTableError(InvalidForeignKeyError):
    """Raised when a foreign key references a non-existent table."""


class MissingFieldError(InvalidForeignKeyError):
    """Raised when a foreign key references a non-existent field."""


class MissingPrimaryKeyError(DataContractValidationError):
    """Raised when a table lacks a primary key or a PK field does not exist."""


class CyclicDependencyError(DataContractValidationError):
    """Raised when foreign key dependencies form a cycle in the table DAG."""


# Backward-compatibility alias
CircularDependencyError = CyclicDependencyError


# ==============================================================================
# Pydantic v2 Data Models
# ==============================================================================


class ForeignKeyDefinition(BaseModel):
    """Represents a relational foreign key constraint from child table to parent table."""
    model_config = ConfigDict(extra="allow")

    field: str = Field(description="Name of the foreign key column in this child table")
    references_table: str = Field(description="Name of the parent referenced table")
    references_field: str = Field(description="Name of the primary key in the parent table")
    relationship_type: str | None = Field(
        default="many_to_one",
        description="Relational cardinality: many_to_one, one_to_one, one_to_many, etc."
    )
    cardinality: str | None = Field(
        default=None,
        description="Mermaid cardinality symbol: ||--o{, ||--||, etc."
    )
    relationship_name: str | None = Field(
        default=None,
        description="Semantic verb or relationship label (e.g. submete, possui)"
    )
    filter_condition: str | None = Field(
        default=None,
        description="Optional filter expression for conditional foreign keys"
    )

    @property
    def target_reference(self) -> str:
        """Normalized string representation: 'table.field'."""
        return f"{self.references_table}.{self.references_field}"


# Backward-compatibility alias
ForeignKeyContract = ForeignKeyDefinition


class BusinessRuleContract(BaseModel):
    """Represents an explicit business logic rule or domain constraint."""
    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, description="Unique identifier for the business rule")
    description: str | None = Field(default=None, description="Human-readable description")
    rule: str | None = Field(default=None, description="Logical rule expression or formula")


class RelationshipContract(BaseModel):
    """Immutable representation of a directed relationship edge between two entities."""
    model_config = ConfigDict(extra="allow")

    parent_table: str
    parent_field: str
    child_table: str
    child_field: str
    relationship_type: str = "many_to_one"
    cardinality_symbol: str = "||--o{"
    label: str = ""
    filter_condition: str | None = None


class FieldContract(BaseModel):
    """Represents a column/field contract within a table schema."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Column name")
    type: str = Field(description="Data type (e.g., string, integer, decimal, date, datetime)")
    nullable: bool = Field(default=False, description="Whether null values are permitted")
    primary_key: bool = Field(default=False, description="Whether this field is a primary key")
    unique: bool = Field(default=False, description="Whether values must be strictly unique")
    foreign_key: str | None = Field(
        default=None,
        description="Foreign key target in 'parent_table.parent_field' notation"
    )
    description: str | None = Field(default=None, description="Semantic field description")
    format: str | None = Field(default=None, description="Data format hint (e.g., uuid, iso8601)")
    faker: str | None = Field(default=None, description="Faker provider method hint (e.g., cnpj, company)")
    regex: str | None = Field(default=None, description="Regular expression pattern constraint")
    min_value: int | float | str | None = Field(default=None, description="Minimum numeric or date bound")
    max_value: int | float | str | None = Field(default=None, description="Maximum numeric or date bound")
    enum_values: list[Any] = Field(default_factory=list, description="Permitted enumeration values")
    rules: list[str] = Field(default_factory=list, description="Column-level validation rules")
    constraints: dict[str, Any] = Field(default_factory=dict, description="Detailed constraint parameters")

    @model_validator(mode="before")
    @classmethod
    def normalize_constraints(cls, data: Any) -> Any:
        """Synchronizes inline constraints dictionary with top-level attributes."""
        if isinstance(data, dict):
            constraints = data.get("constraints") or {}
            if isinstance(constraints, dict):
                for key in ["nullable", "primary_key", "unique", "foreign_key", "regex", "format"]:
                    if key not in data and key in constraints:
                        data[key] = constraints[key]
                    elif key in data and key not in constraints:
                        constraints[key] = data[key]

                if "min" in constraints and "min_value" not in data:
                    data["min_value"] = constraints["min"]
                if "max" in constraints and "max_value" not in data:
                    data["max_value"] = constraints["max"]
                if "enum" in constraints and "enum_values" not in data:
                    data["enum_values"] = constraints["enum"]

                data["constraints"] = constraints
        return data

    @property
    def is_pk(self) -> bool:
        """True if this field is a primary key."""
        return bool(self.primary_key)

    @property
    def is_fk(self) -> bool:
        """True if this field is a foreign key."""
        return bool(self.foreign_key)

    @property
    def is_uk(self) -> bool:
        """True if this field is unique and not a primary key."""
        return bool(self.unique and not self.primary_key)

    @property
    def fk_target_table(self) -> str | None:
        """Parent table name referenced by this foreign key."""
        if self.foreign_key and "." in self.foreign_key:
            return self.foreign_key.split(".", 1)[0]
        return None

    @property
    def fk_target_field(self) -> str | None:
        """Parent field name referenced by this foreign key."""
        if self.foreign_key and "." in self.foreign_key:
            return self.foreign_key.split(".", 1)[1]
        return None

    @property
    def sanitized_mermaid_type(self) -> str:
        """Strip parameters like (255) and illegal characters for Mermaid erDiagram."""
        cleaned = re.sub(r"\(.*?\)", "", str(self.type).strip())
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", cleaned)
        return cleaned.lower() or "string"

    def constraints_summary(self) -> str:
        """Human-readable constraint tokens for CLI / UI rendering."""
        tokens = []
        if self.primary_key:
            tokens.append("PK")
        if not self.nullable:
            tokens.append("NOT NULL")
        if self.unique:
            tokens.append("UNIQUE")
        if self.foreign_key:
            tokens.append(f"FK({self.foreign_key})")
        if self.enum_values:
            tokens.append(f"ENUM[{len(self.enum_values)}]")
        if self.regex:
            tokens.append("REGEX")
        if self.min_value is not None or self.max_value is not None:
            tokens.append(f"RANGE[{self.min_value}..{self.max_value}]")
        return ", ".join(tokens) or "NONE"


class TableContract(BaseModel):
    """Represents an entity table contract within the Data Mesh ecosystem."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Table name identifier")
    description: str | None = Field(default=None, description="Semantic table description")
    primary_key: str | list[str] = Field(description="Primary key column name or composite list")
    sample_size: int | None = Field(default=100, description="Default sample row count for this table")
    fields: list[FieldContract] = Field(description="List of column specifications")
    foreign_keys: list[ForeignKeyDefinition] = Field(
        default_factory=list,
        description="List of table-level foreign key definitions"
    )
    business_rules: list[str | BusinessRuleContract | dict[str, Any]] = Field(
        default_factory=list,
        description="Table-specific business rules"
    )

    @model_validator(mode="after")
    def sync_and_validate_table(self) -> TableContract:
        """Validates fields, synchronizes primary keys and reconciles foreign keys."""
        # 1. Enforce unique field names within the table
        field_names = [f.name for f in self.fields]
        if len(field_names) != len(set(field_names)):
            duplicates = [n for n in field_names if field_names.count(n) > 1]
            raise DuplicateFieldError(f"Duplicate fields detected in table '{self.name}': {set(duplicates)}")

        # 2. Validate and sync Primary Key
        pk_list = [self.primary_key] if isinstance(self.primary_key, str) else list(self.primary_key)
        if not pk_list:
            raise MissingPrimaryKeyError(f"Table '{self.name}' must have at least one primary key defined.")

        field_map = {f.name: f for f in self.fields}
        for pk in pk_list:
            if pk not in field_map:
                raise MissingPrimaryKeyError(
                    f"Primary key '{pk}' specified in table '{self.name}' not found among table fields."
                )
            field_map[pk].primary_key = True
            if field_map[pk].nullable:
                raise DataContractValidationError(
                    f"Primary key '{pk}' in table '{self.name}' cannot have nullable=True."
                )

        # 3. Reconcile foreign keys between field-level and table-level
        for fk in self.foreign_keys:
            if fk.field in field_map and not field_map[fk.field].foreign_key:
                field_map[fk.field].foreign_key = f"{fk.references_table}.{fk.references_field}"

        existing_fks = {(fk.field, fk.references_table, fk.references_field) for fk in self.foreign_keys}
        for f in self.fields:
            if f.foreign_key:
                parts = f.foreign_key.split(".")
                if len(parts) == 2:
                    ref_table, ref_field = parts
                    if (f.name, ref_table, ref_field) not in existing_fks:
                        self.foreign_keys.append(
                            ForeignKeyDefinition(
                                field=f.name,
                                references_table=ref_table,
                                references_field=ref_field,
                            )
                        )
                        existing_fks.add((f.name, ref_table, ref_field))
                else:
                    raise InvalidForeignKeyError(
                        f"Invalid foreign_key format '{f.foreign_key}' on field '{f.name}'. Expected 'table.field'."
                    )

        return self

    def get_field(self, field_name: str) -> FieldContract | None:
        """Returns the FieldContract by name or None if not found."""
        for f in self.fields:
            if f.name == field_name:
                return f
        for f in self.fields:
            if f.name.lower() == field_name.lower():
                return f
        return None

    def get_primary_keys(self) -> list[str]:
        """Returns the list of primary key field names."""
        return [self.primary_key] if isinstance(self.primary_key, str) else list(self.primary_key)

    def get_foreign_keys(self) -> list[ForeignKeyDefinition]:
        """Returns all foreign key definitions for this table."""
        return self.foreign_keys

    def get_dependencies(self) -> list[str]:
        """Returns distinct parent table names that this table references (excluding self-references)."""
        deps: set[str] = set()
        for fk in self.foreign_keys:
            if fk.references_table != self.name:
                deps.add(fk.references_table)
        return sorted(deps)

    @property
    def field_names(self) -> list[str]:
        """List of all field names in this table."""
        return [f.name for f in self.fields]

    @property
    def primary_key_fields(self) -> list[str]:
        """List of primary key field names."""
        return self.get_primary_keys()

    @property
    def foreign_key_fields(self) -> list[FieldContract]:
        """List of FieldContract objects that define a foreign key."""
        return [f for f in self.fields if f.foreign_key]

    @property
    def referenced_tables(self) -> set[str]:
        """Set of parent table names referenced by this table's foreign keys."""
        return {fk.references_table for fk in self.foreign_keys}


class DataContract(BaseModel):
    """Root specification for a Data Mesh Data Contract."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    mesh_name: str = Field(
        validation_alias=AliasChoices("mesh_name", "dataset_name"),
        description="Identifier of the data mesh ecosystem or dataset"
    )
    version: str = Field(
        default="1.0.0",
        validation_alias=AliasChoices("version", "data_contract_version"),
        description="Contract semantic version"
    )
    domain: str | None = Field(default="default", description="Business domain (e.g. credit_risk)")
    description: str | None = Field(default=None, description="Contract overview")
    owner: str | None = Field(default=None, description="Team or engineer owning the contract")
    locale: str = Field(default="pt_BR", description="Locale for synthetic Faker generation")
    default_sample_size: int = Field(default=100, description="Default sample row count for entities")
    tables: list[TableContract] = Field(description="Tables defined in this mesh contract")
    business_rules: list[str | BusinessRuleContract | dict[str, Any]] = Field(
        default_factory=list,
        description="Global cross-table business rules"
    )

    @property
    def dataset_name(self) -> str:
        """Alias for mesh_name."""
        return self.mesh_name

    @property
    def data_contract_version(self) -> str:
        """Alias for version."""
        return self.version

    @property
    def table_names(self) -> list[str]:
        """List of table names in definition order."""
        return self.get_table_names()

    @model_validator(mode="after")
    def validate_contract_integrity(self) -> DataContract:
        """Validates table uniqueness, referential integrity across tables, and DAG acyclicity."""
        if not self.tables:
            raise DataContractValidationError("DataContract must define at least one table.")

        # 1. Check duplicate table names
        table_names = [t.name for t in self.tables]
        if len(table_names) != len(set(table_names)):
            dups = [n for n in table_names if table_names.count(n) > 1]
            raise DuplicateTableError(f"Duplicate tables detected in contract: {set(dups)}")

        table_map = {t.name: t for t in self.tables}

        # 2. Check referential integrity for all Foreign Keys
        for table in self.tables:
            for fk in table.foreign_keys:
                if fk.references_table not in table_map:
                    raise MissingTableError(
                        f"Foreign key in table '{table.name}' on field '{fk.field}' "
                        f"references non-existent table '{fk.references_table}'."
                    )
                target_table = table_map[fk.references_table]
                target_field = target_table.get_field(fk.references_field)
                if not target_field:
                    raise MissingFieldError(
                        f"Foreign key in table '{table.name}' on field '{fk.field}' "
                        f"references non-existent field '{fk.references_field}' in table '{fk.references_table}'."
                    )

        # 3. Verify topological sorting and cycle freedom
        self.get_dag_order()
        return self

    @property
    def name(self) -> str:
        """Alias for mesh_name."""
        return self.mesh_name

    def get_table(self, name: str) -> TableContract | None:
        """Returns TableContract by table name or None."""
        for t in self.tables:
            if t.name == name:
                return t
        for t in self.tables:
            if t.name.lower() == name.lower():
                return t
        return None

    def get_table_names(self) -> list[str]:
        """Returns list of table names in definition order."""
        return [t.name for t in self.tables]

    def topological_sort(self) -> list[str]:
        """Alias for get_dag_order."""
        return self.get_dag_order()

    def get_dag_order(self) -> list[str]:
        """
        Computes the topological dependency order using Kahn's algorithm.
        Guarantees parent tables appear before child tables.
        Raises CyclicDependencyError with informative path tracing if a cycle is found.
        """
        table_names = [t.name for t in self.tables]
        in_degree: dict[str, int] = {name: 0 for name in table_names}
        children: dict[str, set[str]] = {name: set() for name in table_names}

        for table in self.tables:
            parents = set(table.get_dependencies())
            in_degree[table.name] = len(parents)
            for parent in parents:
                if parent in children:
                    children[parent].add(table.name)

        # Queue nodes with 0 incoming dependencies (root tables)
        queue: list[str] = sorted([name for name in table_names if in_degree[name] == 0])
        ordered: list[str] = []

        while queue:
            node = queue.pop(0)
            ordered.append(node)

            for child in sorted(children.get(node, set())):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
            queue.sort()

        if len(ordered) != len(table_names):
            remaining = [name for name, deg in in_degree.items() if deg > 0]
            cycle_path = self._trace_cycle_path(remaining)
            raise CyclicDependencyError(
                f"Circular foreign key dependency detected among tables: {remaining}. Cycle path: {cycle_path}"
            )

        return ordered

    def _trace_cycle_path(self, cycle_nodes: list[str]) -> str:
        """Finds and formats a representative cycle path for debugging."""
        cycle_set = set(cycle_nodes)
        table_map = {t.name: t for t in self.tables if t.name in cycle_set}
        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        stack: list[str] = []

        def dfs(u: str) -> list[str] | None:
            visited[u] = 1
            stack.append(u)
            for v in table_map[u].get_dependencies():
                if v in cycle_set:
                    if visited.get(v, 0) == 1:
                        idx = stack.index(v)
                        return stack[idx:] + [v]
                    if visited.get(v, 0) == 0:
                        res = dfs(v)
                        if res:
                            return res
            stack.pop()
            visited[u] = 2
            return None

        for node in cycle_nodes:
            if visited.get(node, 0) == 0:
                cycle = dfs(node)
                if cycle:
                    return " -> ".join(cycle)
        return " -> ".join(cycle_nodes)

    def get_relationships(self) -> list[RelationshipContract]:
        """Extracts complete relationship list with inferred Mermaid cardinalities."""
        relationships: list[RelationshipContract] = []
        for table in self.tables:
            for fk in table.foreign_keys:
                child_field = table.get_field(fk.field)

                if fk.cardinality:
                    cardinality = fk.cardinality
                elif fk.relationship_type == "one_to_one":
                    cardinality = "||--||"
                elif fk.relationship_type == "many_to_one":
                    cardinality = "||--o{"
                elif child_field and child_field.unique:
                    cardinality = "||--||"
                else:
                    cardinality = "||--o{"

                label = fk.relationship_name or fk.relationship_type or fk.field

                relationships.append(
                    RelationshipContract(
                        parent_table=fk.references_table,
                        parent_field=fk.references_field,
                        child_table=table.name,
                        child_field=fk.field,
                        relationship_type=fk.relationship_type or "many_to_one",
                        cardinality_symbol=cardinality,
                        label=label,
                        filter_condition=fk.filter_condition,
                    )
                )
        return relationships

    def to_dict(self) -> dict[str, Any]:
        """Serializes the DataContract to a Python dictionary."""
        return self.model_dump()

    def to_prompt_context(self) -> str:
        """Generates a dense markdown schema summary for LLM prompt context injection."""
        lines = [
            f"# Data Mesh Contract: {self.mesh_name} (v{self.version})",
            f"Domain: {self.domain} | Locale: {self.locale}",
            "",
            "## Table Generation Order (Topological DAG):",
            " -> ".join(self.get_dag_order()),
            "",
            "## Tables & Schema:",
        ]
        for t in self.tables:
            lines.append(f"### Table: {t.name} (Sample Size: {t.sample_size})")
            if t.description:
                lines.append(f"Description: {t.description}")
            lines.append("Columns:")
            for f in t.fields:
                desc = f" - {f.description}" if f.description else ""
                lines.append(f"  - `{f.name}` ({f.type}): {f.constraints_summary()}{desc}")
            if t.business_rules:
                lines.append("Business Rules:")
                for rule in t.business_rules:
                    if isinstance(rule, BusinessRuleContract):
                        rule_str = f"[{rule.id}] {rule.description or rule.rule}"
                    elif isinstance(rule, dict):
                        rule_str = f"[{rule.get('id', '')}] {rule.get('description', '') or rule.get('rule', '')}"
                    else:
                        rule_str = str(rule)
                    lines.append(f"  - {rule_str}")
            lines.append("")

        if self.business_rules:
            lines.append("## Global Business Rules:")
            for rule in self.business_rules:
                if isinstance(rule, BusinessRuleContract):
                    rule_str = f"[{rule.id}] {rule.description or rule.rule}"
                elif isinstance(rule, dict):
                    rule_str = f"[{rule.get('id', '')}] {rule.get('description', '') or rule.get('rule', '')}"
                else:
                    rule_str = str(rule)
                lines.append(f"  - {rule_str}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_yaml(cls, yaml_source: str | Path) -> DataContract:
        """Parses a DataContract instance from a YAML string or file path."""
        try:
            if isinstance(yaml_source, Path) or (
                isinstance(yaml_source, str) and "\n" not in yaml_source and Path(yaml_source).is_file()
            ):
                content = Path(yaml_source).read_text(encoding="utf-8")
            else:
                content = str(yaml_source)
            if not content or not content.strip():
                raise DataContractValidationError("Contract YAML content is empty.")
            raw = yaml.safe_load(content)
        except (DataContractError, yaml.YAMLError) as e:
            if isinstance(e, DataContractError):
                raise
            raise ContractParseError(f"Failed to parse YAML content: {e}") from e
        except Exception as e:
            raise ContractParseError(f"Failed to parse YAML content: {e}") from e

        if not isinstance(raw, dict):
            raise ContractParseError(f"YAML content must be a valid mapping dictionary, got {type(raw).__name__}.")

        return cls.model_validate(raw)

    def to_yaml(self) -> str:
        """Serializes the DataContract to a YAML formatted string."""
        data = self.model_dump(exclude_none=True, by_alias=True)
        return yaml.dump(data, sort_keys=False, allow_unicode=True)


# ==============================================================================
# Top-Level Utility Functions
# ==============================================================================


def load_contract(file_path: str | Path) -> DataContract:
    """
    Loads and validates a contract YAML file from disk.

    Raises:
        ContractFileNotFoundError: If the file does not exist.
        ContractParseError: If YAML syntax is invalid.
        DataContractValidationError: If schema validation fails.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ContractFileNotFoundError(f"Contract file not found at '{path.resolve()}'.")

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise DataContractError(f"Failed to read contract file '{path}': {e}") from e

    return parse_contract_from_string(content)


def parse_contract(source: str | Path) -> DataContract:
    """
    Polymorphic loader: accepts either a file path or a raw YAML string.
    """
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        return load_contract(source)
    return parse_contract_from_string(str(source))


def parse_contract_from_string(yaml_content: str) -> DataContract:
    """
    Parses and validates a contract from raw YAML string.

    Raises:
        ContractParseError: If YAML syntax is invalid.
        DataContractValidationError: If schema validation fails.
    """
    return DataContract.from_yaml(yaml_content)


def safe_parse_contract(source: str | Path) -> tuple[DataContract | None, str | None]:
    """
    Non-throwing safe parsing utility for UI and interactive CLI flows.
    Returns (DataContract, None) on success or (None, error_message) on failure.
    """
    try:
        contract = parse_contract(source)
        return contract, None
    except (DataContractError, yaml.YAMLError, ValueError, TypeError, OSError) as e:
        return None, str(e)
