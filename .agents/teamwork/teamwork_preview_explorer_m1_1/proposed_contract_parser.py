"""Simula-AI Data Contract Parser & Validator.

Ingests YAML data contracts, validates multi-table relational schemas via Pydantic v2,
resolves table dependency DAGs using Kahn's topological sort, and validates referential integrity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
import yaml

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ==============================================================================
# Custom Exceptions Hierarchy
# ==============================================================================


class DataContractError(Exception):
    """Base exception for all data contract errors."""
    pass


class ContractParseError(DataContractError):
    """Raised when YAML syntax is invalid or cannot be parsed."""
    pass


class DataContractValidationError(DataContractError):
    """Raised when contract content violates schema or relational rules."""
    pass


class DuplicateTableError(DataContractValidationError):
    """Raised when duplicate table names are detected in the contract."""
    pass


class DuplicateFieldError(DataContractValidationError):
    """Raised when duplicate field names are detected within a table."""
    pass


class MissingTableError(DataContractValidationError):
    """Raised when a foreign key references a non-existent table."""
    pass


class MissingFieldError(DataContractValidationError):
    """Raised when a foreign key references a non-existent field."""
    pass


class MissingPrimaryKeyError(DataContractValidationError):
    """Raised when a table lacks a primary key or a PK field does not exist."""
    pass


class InvalidForeignKeyError(DataContractValidationError):
    """Raised when a foreign key format is invalid or references are malformed."""
    pass


class CyclicDependencyError(DataContractValidationError):
    """Raised when foreign key dependencies form a cycle in the table DAG."""
    pass


# ==============================================================================
# Pydantic v2 Data Models
# ==============================================================================


class ForeignKeyDefinition(BaseModel):
    """Represents a relational foreign key constraint from child table to parent table."""
    model_config = ConfigDict(extra="allow")

    field: str = Field(description="Name of the foreign key column in this child table")
    references_table: str = Field(description="Name of the parent referenced table")
    references_field: str = Field(description="Name of the primary key in the parent table")
    relationship_type: Optional[str] = Field(
        default="many_to_one",
        description="Relational cardinality: many_to_one, one_to_one, one_to_many, etc."
    )
    filter_condition: Optional[str] = Field(
        default=None,
        description="Optional filter expression for conditional foreign keys"
    )


class BusinessRuleContract(BaseModel):
    """Represents an explicit business logic rule or domain constraint."""
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None, description="Unique identifier for the business rule")
    description: Optional[str] = Field(default=None, description="Human-readable description")
    rule: Optional[str] = Field(default=None, description="Logical rule expression or formula")


class FieldContract(BaseModel):
    """Represents a column/field contract within a table schema."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Column name")
    type: str = Field(description="Data type (e.g., string, integer, decimal, date, datetime)")
    nullable: bool = Field(default=False, description="Whether null values are permitted")
    primary_key: bool = Field(default=False, description="Whether this field is a primary key")
    unique: bool = Field(default=False, description="Whether values must be strictly unique")
    foreign_key: Optional[str] = Field(
        default=None,
        description="Foreign key target in 'parent_table.parent_field' notation"
    )
    description: Optional[str] = Field(default=None, description="Semantic field description")
    format: Optional[str] = Field(default=None, description="Data format hint (e.g., uuid, iso8601)")
    faker: Optional[str] = Field(default=None, description="Faker provider method hint (e.g., cnpj, company)")
    rules: List[str] = Field(default_factory=list, description="Column-level validation rules")
    constraints: Dict[str, Any] = Field(default_factory=dict, description="Detailed constraint parameters")

    @model_validator(mode="before")
    @classmethod
    def normalize_constraints(cls, data: Any) -> Any:
        """Synchronizes inline constraints dictionary with top-level attributes."""
        if isinstance(data, dict):
            constraints = data.get("constraints") or {}
            # Sync constraints dict into top-level model fields if not already populated
            for key in ["nullable", "primary_key", "unique", "foreign_key"]:
                if key not in data and key in constraints:
                    data[key] = constraints[key]
                elif key in data and key not in constraints:
                    constraints[key] = data[key]
            data["constraints"] = constraints
        return data


class TableContract(BaseModel):
    """Represents an entity table contract within the Data Mesh ecosystem."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Table name identifier")
    description: Optional[str] = Field(default=None, description="Semantic table description")
    primary_key: Union[str, List[str]] = Field(description="Primary key column name or composite list")
    sample_size: Optional[int] = Field(default=None, description="Default sample row count for this table")
    fields: List[FieldContract] = Field(description="List of column specifications")
    foreign_keys: List[ForeignKeyDefinition] = Field(
        default_factory=list,
        description="List of table-level foreign key definitions"
    )
    business_rules: List[Union[str, BusinessRuleContract, Dict[str, Any]]] = Field(
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

    def get_field(self, field_name: str) -> Optional[FieldContract]:
        """Returns the FieldContract by name or None if not found."""
        for f in self.fields:
            if f.name == field_name:
                return f
        return None

    def get_primary_keys(self) -> List[str]:
        """Returns the list of primary key field names."""
        return [self.primary_key] if isinstance(self.primary_key, str) else list(self.primary_key)

    def get_foreign_keys(self) -> List[ForeignKeyDefinition]:
        """Returns all foreign key definitions for this table."""
        return self.foreign_keys

    def get_dependencies(self) -> List[str]:
        """Returns distinct parent table names that this table references (excluding self-references)."""
        deps: Set[str] = set()
        for fk in self.foreign_keys:
            if fk.references_table != self.name:
                deps.add(fk.references_table)
        return sorted(list(deps))


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
    domain: Optional[str] = Field(default=None, description="Business domain (e.g. credit_risk)")
    description: Optional[str] = Field(default=None, description="Contract overview")
    owner: Optional[str] = Field(default=None, description="Team or engineer owning the contract")
    locale: str = Field(default="pt_BR", description="Locale for synthetic Faker generation")
    default_sample_size: int = Field(default=100, description="Default sample row count for entities")
    tables: List[TableContract] = Field(description="Tables defined in this mesh contract")
    business_rules: List[Union[str, BusinessRuleContract, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Global cross-table business rules"
    )

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

    def get_table(self, name: str) -> Optional[TableContract]:
        """Returns TableContract by table name or None."""
        for t in self.tables:
            if t.name == name:
                return t
        return None

    def get_table_names(self) -> List[str]:
        """Returns list of table names in definition order."""
        return [t.name for t in self.tables]

    def get_dag_order(self) -> List[str]:
        """
        Computes the topological dependency order using Kahn's algorithm.
        Guarantees parent tables appear before child tables.
        Raises CyclicDependencyError with informative path tracing if a cycle is found.
        """
        table_names = [t.name for t in self.tables]
        in_degree: Dict[str, int] = {name: 0 for name in table_names}
        children: Dict[str, Set[str]] = {name: set() for name in table_names}

        for table in self.tables:
            parents = set(table.get_dependencies())
            in_degree[table.name] = len(parents)
            for parent in parents:
                if parent in children:
                    children[parent].add(table.name)

        # Queue nodes with 0 incoming dependencies (root tables)
        queue: List[str] = sorted([name for name in table_names if in_degree[name] == 0])
        ordered: List[str] = []

        while queue:
            node = queue.pop(0)
            ordered.append(node)

            for child in sorted(list(children.get(node, set()))):
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

    def _trace_cycle_path(self, cycle_nodes: List[str]) -> str:
        """Finds and formats a representative cycle path for debugging."""
        cycle_set = set(cycle_nodes)
        table_map = {t.name: t for t in self.tables if t.name in cycle_set}
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        stack: List[str] = []

        def dfs(u: str) -> Optional[List[str]]:
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

    @classmethod
    def from_yaml(cls, yaml_source: Union[str, Path]) -> DataContract:
        """Parses a DataContract instance from a YAML string or file path."""
        try:
            if isinstance(yaml_source, Path) or (
                isinstance(yaml_source, str) and "\n" not in yaml_source and Path(yaml_source).is_file()
            ):
                content = Path(yaml_source).read_text(encoding="utf-8")
            else:
                content = str(yaml_source)
            raw = yaml.safe_load(content)
        except Exception as e:
            raise ContractParseError(f"Failed to parse YAML content: {e}") from e

        if not isinstance(raw, dict):
            raise ContractParseError("YAML content must be a valid mapping dictionary.")

        return cls.model_validate(raw)

    def to_yaml(self) -> str:
        """Serializes the DataContract to a YAML formatted string."""
        data = self.model_dump(exclude_none=True, by_alias=True)
        return yaml.dump(data, sort_keys=False, allow_unicode=True)
