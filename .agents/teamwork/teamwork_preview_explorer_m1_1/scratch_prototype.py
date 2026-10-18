"""Prototype for testing DataContract models, DAG topological sorting, and validation."""
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, AliasChoices, ConfigDict, model_validator, field_validator


# --- Custom Exceptions Hierarchy ---
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
    """Raised when duplicate table names are detected."""
    pass


class DuplicateFieldError(DataContractValidationError):
    """Raised when duplicate field names are detected in a table."""
    pass


class MissingTableError(DataContractValidationError):
    """Raised when a referenced table is not found."""
    pass


class MissingFieldError(DataContractValidationError):
    """Raised when a referenced field is not found."""
    pass


class MissingPrimaryKeyError(DataContractValidationError):
    """Raised when a table lacks a primary key or PK field does not exist."""
    pass


class InvalidForeignKeyError(DataContractValidationError):
    """Raised when a foreign key specification is malformed or broken."""
    pass


class CyclicDependencyError(DataContractValidationError):
    """Raised when foreign key dependencies form a cycle in the DAG."""
    pass


# --- Pydantic Models ---
class ForeignKeyDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str
    references_table: str
    references_field: str
    relationship_type: Optional[str] = "many_to_one"
    filter_condition: Optional[str] = None


class FieldContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    nullable: bool = False
    primary_key: bool = False
    unique: bool = False
    foreign_key: Optional[str] = None  # format: "table.field"
    description: Optional[str] = None
    format: Optional[str] = None
    faker: Optional[str] = None
    rules: List[str] = Field(default_factory=list)
    constraints: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_constraints(cls, data: Any) -> Any:
        if isinstance(data, dict):
            constraints = data.get("constraints") or {}
            if "nullable" not in data and "nullable" in constraints:
                data["nullable"] = constraints["nullable"]
            if "primary_key" not in data and "primary_key" in constraints:
                data["primary_key"] = constraints["primary_key"]
            if "unique" not in data and "unique" in constraints:
                data["unique"] = constraints["unique"]
            if "foreign_key" not in data and "foreign_key" in constraints:
                data["foreign_key"] = constraints["foreign_key"]

            # Ensure constraints dict is synced
            if "nullable" in data and "nullable" not in constraints:
                constraints["nullable"] = data["nullable"]
            if "primary_key" in data and "primary_key" not in constraints:
                constraints["primary_key"] = data["primary_key"]
            if "unique" in data and "unique" not in constraints:
                constraints["unique"] = data["unique"]
            if "foreign_key" in data and "foreign_key" not in constraints:
                constraints["foreign_key"] = data["foreign_key"]
            data["constraints"] = constraints
        return data


class TableContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: Optional[str] = None
    primary_key: Union[str, List[str]]
    sample_size: Optional[int] = None
    fields: List[FieldContract]
    foreign_keys: List[ForeignKeyDefinition] = Field(default_factory=list)
    business_rules: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_table_metadata(self) -> "TableContract":
        # 1. Check duplicate fields
        field_names = [f.name for f in self.fields]
        if len(field_names) != len(set(field_names)):
            duplicates = [name for name in field_names if field_names.count(name) > 1]
            raise DuplicateFieldError(f"Duplicate fields in table '{self.name}': {set(duplicates)}")

        # 2. Sync PK
        pk_list = [self.primary_key] if isinstance(self.primary_key, str) else self.primary_key
        if not pk_list:
            raise MissingPrimaryKeyError(f"Table '{self.name}' must have at least one primary key defined.")
        
        field_map = {f.name: f for f in self.fields}
        for pk in pk_list:
            if pk not in field_map:
                raise MissingPrimaryKeyError(f"Primary key '{pk}' not found in fields of table '{self.name}'.")
            field_map[pk].primary_key = True
            if field_map[pk].nullable:
                raise DataContractValidationError(f"Primary key '{pk}' in table '{self.name}' cannot be nullable.")

        # 3. Sync FKs between field-level and table-level
        # Reconcile table.foreign_keys -> field.foreign_key
        for fk in self.foreign_keys:
            if fk.field in field_map:
                field_map[fk.field].foreign_key = f"{fk.references_table}.{fk.references_field}"

        # Reconcile field.foreign_key -> table.foreign_keys
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
        for f in self.fields:
            if f.name == field_name:
                return f
        return None

    def get_primary_keys(self) -> List[str]:
        return [self.primary_key] if isinstance(self.primary_key, str) else list(self.primary_key)

    def get_dependencies(self) -> List[str]:
        """Returns list of distinct parent tables this table depends on (excluding self-references)."""
        deps = set()
        for fk in self.foreign_keys:
            if fk.references_table != self.name:
                deps.add(fk.references_table)
        return sorted(list(deps))


class DataContract(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    mesh_name: str = Field(validation_alias=AliasChoices("mesh_name", "dataset_name"))
    version: str = Field(default="1.0.0", validation_alias=AliasChoices("version", "data_contract_version"))
    domain: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    locale: str = "pt_BR"
    default_sample_size: int = 100
    tables: List[TableContract]
    business_rules: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contract_integrity(self) -> "DataContract":
        if not self.tables:
            raise DataContractValidationError("DataContract must contain at least one table.")

        # Check duplicate tables
        table_names = [t.name for t in self.tables]
        if len(table_names) != len(set(table_names)):
            dups = [name for name in table_names if table_names.count(name) > 1]
            raise DuplicateTableError(f"Duplicate tables in contract: {set(dups)}")

        table_map = {t.name: t for t in self.tables}

        # Check referential integrity for all FKs
        for table in self.tables:
            for fk in table.foreign_keys:
                if fk.references_table not in table_map:
                    raise MissingTableError(
                        f"Foreign key in table '{table.name}' on field '{fk.field}' references unknown table '{fk.references_table}'."
                    )
                target_table = table_map[fk.references_table]
                target_field = target_table.get_field(fk.references_field)
                if not target_field:
                    raise MissingFieldError(
                        f"Foreign key in table '{table.name}' on field '{fk.field}' references non-existent field '{fk.references_field}' in table '{fk.references_table}'."
                    )

        # Validate DAG dependencies for circular references
        self.get_dag_order()
        return self

    def get_table(self, name: str) -> Optional[TableContract]:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    def get_table_names(self) -> List[str]:
        return [t.name for t in self.tables]

    def get_dag_order(self) -> List[str]:
        """
        Calculates topological order of tables for data generation using Kahn's algorithm.
        Parent tables appear before dependent child tables.
        Raises CyclicDependencyError if circular dependency is detected.
        """
        table_names = [t.name for t in self.tables]
        
        # in_degree: number of distinct parent tables a table depends on
        # children: map from parent table to set of child tables that depend on it
        in_degree: Dict[str, int] = {name: 0 for name in table_names}
        children: Dict[str, Set[str]] = {name: set() for name in table_names}

        for table in self.tables:
            parent_tables = set(table.get_dependencies())
            in_degree[table.name] = len(parent_tables)
            for parent in parent_tables:
                if parent in children:
                    children[parent].add(table.name)

        # Queue contains tables with 0 incoming dependencies (root tables)
        # Sort queue initially to ensure deterministic ordering
        queue: List[str] = sorted([name for name in table_names if in_degree[name] == 0])
        ordered: List[str] = []

        while queue:
            node = queue.pop(0)
            ordered.append(node)

            # For each dependent child, decrement its in_degree
            for child in sorted(list(children.get(node, set()))):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
            # Keep queue sorted for determinism
            queue.sort()

        if len(ordered) != len(table_names):
            # Cycle detected! Extract cycle info for helpful error message
            remaining = [name for name, deg in in_degree.items() if deg > 0]
            cycle_path = self._find_cycle_path(remaining)
            raise CyclicDependencyError(
                f"Circular foreign key dependency detected among tables: {remaining}. Cycle path: {cycle_path}"
            )

        return ordered

    def _find_cycle_path(self, cycle_nodes: List[str]) -> str:
        """Finds a representative cycle path among the given nodes for diagnostic messages."""
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
                        # Cycle found!
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
    def from_yaml(cls, yaml_source: Union[str, Path]) -> "DataContract":
        """Parses DataContract from a YAML string or file path."""
        try:
            if isinstance(yaml_source, Path) or (isinstance(yaml_source, str) and "\n" not in yaml_source and Path(yaml_source).is_file()):
                path = Path(yaml_source)
                content = path.read_text(encoding="utf-8")
            else:
                content = str(yaml_source)
            raw_dict = yaml.safe_load(content)
        except Exception as e:
            raise ContractParseError(f"Failed to parse YAML content: {e}") from e

        if not isinstance(raw_dict, dict):
            raise ContractParseError("YAML content must be a valid mapping / dictionary.")

        return cls.model_validate(raw_dict)

    def to_yaml(self) -> str:
        """Serializes DataContract to YAML string."""
        data = self.model_dump(exclude_none=True, by_alias=True)
        return yaml.dump(data, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    print("Testing scratch prototype...")
    # Test valid contract
    yaml_sample = """
data_contract_version: "1.0.0"
dataset_name: "credit_mesh_ecosystem"
domain: "credit_risk"
tables:
  - name: "empresas"
    primary_key: "empresa_id"
    fields:
      - name: "empresa_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "cnpj"
        type: "string"
        constraints:
          nullable: false
          unique: true
  - name: "propostas"
    primary_key: "proposta_id"
    fields:
      - name: "proposta_id"
        type: "string"
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas.empresa_id"
  - name: "garantias"
    primary_key: "garantia_id"
    fields:
      - name: "garantia_id"
        type: "string"
      - name: "proposta_id"
        type: "string"
        foreign_key: "propostas.proposta_id"
  - name: "operacoes"
    primary_key: "operacao_id"
    fields:
      - name: "operacao_id"
        type: "string"
      - name: "proposta_id"
        type: "string"
        foreign_key: "propostas.proposta_id"
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas.empresa_id"
"""
    contract = DataContract.from_yaml(yaml_sample)
    print("Mesh Name:", contract.mesh_name)
    print("Tables:", [t.name for t in contract.tables])
    dag_order = contract.get_dag_order()
    print("DAG Order:", dag_order)
    assert dag_order == ["empresas", "propostas", "garantias", "operacoes"] or dag_order == ["empresas", "propostas", "operacoes", "garantias"]
    print("Topological order test passed!")

    # Test Cycle Detection
    cycle_yaml = """
mesh_name: "cycle_mesh"
version: "1.0.0"
tables:
  - name: "table_a"
    primary_key: "id_a"
    fields:
      - name: "id_a"
        type: "string"
      - name: "id_b"
        type: "string"
        foreign_key: "table_b.id_b"
  - name: "table_b"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "id_a"
        type: "string"
        foreign_key: "table_a.id_a"
"""
    try:
        DataContract.from_yaml(cycle_yaml)
        assert False, "Should have raised CyclicDependencyError!"
    except CyclicDependencyError as e:
        print("Successfully caught cycle:", e)

    # Test Missing Table
    missing_table_yaml = """
mesh_name: "test"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
      - name: "fk"
        type: "string"
        foreign_key: "non_existent.id"
"""
    try:
        DataContract.from_yaml(missing_table_yaml)
        assert False, "Should have raised MissingTableError!"
    except MissingTableError as e:
        print("Successfully caught missing table:", e)

    print("All prototype tests passed!")
