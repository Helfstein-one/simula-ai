# Milestone 1 Integration Contracts & Interface Guarantees Specification

**Author**: Explorer 3 (Milestone 1 — Interface & Contract Specification)  
**Date**: 2026-10-12  
**Target Module**: `core/contract_parser.py` and downstream integrations  
**Downstream Consumers**: `core/graph.py` (M2), `core/diagram.py` (M3), `core/exporter.py` (M4), `cli/main.py` (M5), `ui/app.py` (M5)

---

## 1. Executive Summary & Integration Architecture

Milestone 1 establishes the structural foundation of Simula-AI. `core/contract_parser.py` serves as the authoritative single source of truth for schema representation, relational topology, and data constraints across the entire framework.

```
                              ┌─────────────────────────────────────────┐
                              │    contracts/exemplo_credito_mesh.yaml  │
                              └────────────────────┬────────────────────┘
                                                   │
                                                   ▼
                              ┌─────────────────────────────────────────┐
                              │         core/contract_parser.py         │
                              │  - Pydantic v2 Models (DataContract)    │
                              │  - Schema Validation & Error Hierarchy  │
                              │  - Kahn's Algorithm DAG Topological Sort│
                              │  - Relational & Cardinality Extraction  │
                              └──────┬─────────────┬─────────────┬──────┘
                                     │             │             │
             ┌───────────────────────┘             │             └───────────────────────┐
             ▼                                     ▼                                     ▼
┌──────────────────────────┐     ┌───────────────────────────┐     ┌──────────────────────────┐
│  M2: core/graph.py       │     │  M3: core/diagram.py      │     │  M4: core/exporter.py    │
│  (CoALA Cognitive Loop)  │     │  (Mermaid ER Engine)      │     │  (Deliverables Exporter) │
│  - DAG generation order  │     │  - Sanitized types        │     │  - Topological sort      │
│  - Prompt schema context │     │  - PK / FK / UK markers   │     │  - Target columns & types│
│  - Episodic memory basis │     │  - Cardinality & labels   │     │  - Sample sizes          │
└────────────┬─────────────┘     └─────────────┬─────────────┘     └─────────────┬────────────┘
             │                                 │                                 │
             └───────────────────────┬─────────┴─────────────────────────────────┘
                                     ▼
                      ┌─────────────────────────────┐
                      │    M5: Dual User Interface  │
                      │  - cli/main.py (Typer/Rich) │
                      │  - ui/app.py (Streamlit)    │
                      └─────────────────────────────┘
```

---

## 2. Downstream Consumer Requirements & Guarantees

### 2.1 Consumer 1: `core/graph.py` (M2 — CoALA Cognitive Loop)

#### Role & Interaction
`core/graph.py` implements the LangGraph StateGraph (`node_initialize`, `node_generate`, `node_execute`, `route_decision`). At `node_initialize`, it parses the contract and initializes `SimulaState`.

#### Guarantees Provided by `core/contract_parser.py`:
1. **Topological Order Guidance**:
   `contract.get_dag_order() -> List[str]` guarantees that parent entities appear before dependent child entities (e.g., `empresas -> propostas -> garantias, operacoes`). This sequence is injected into `procedural_memory` so the LLM constructs generators in strictly valid FK order.
2. **Deterministic LLM Context Injection**:
   `contract.to_prompt_context() -> str` produces a dense, structured markdown summary of tables, columns, types, foreign keys, and business rules, eliminating hallucinated schemas.
3. **Fail-Fast Schema Validation**:
   `load_contract()` raises specific `ContractValidationError` or `CircularDependencyError` before the agent initiates token-consuming LLM calls.
4. **State Serialization**:
   `contract.to_dict()` provides a JSON-serializable dictionary for `SimulaState["working_memory"]["contract_dict"]`.

### 2.2 Consumer 2: `core/diagram.py` (M3 — Hybrid Mermaid ER Engine)

#### Role & Interaction
`core/diagram.py` renders interactive Mermaid ER diagrams for CLI output (`mesh_er_diagram.mmd`) and Streamlit UI embedding.

#### Guarantees Provided by `core/contract_parser.py`:
1. **Sanitized Attribute Types**:
   `field.sanitized_mermaid_type -> str` strips SQL/YAML parameterization (e.g. `decimal(10,2)` -> `decimal`, `varchar(255)` -> `varchar`, `timestamp without time zone` -> `timestamp`) and non-alphanumeric characters, preventing Mermaid parser breakage.
2. **Formal Key Classification**:
   `field.is_pk`, `field.is_fk`, `field.is_uk` provide deterministic key markers (`PK`, `FK`, `UK`).
3. **Deterministic Relationship Edges**:
   `contract.get_relationships() -> List[RelationshipContract]` exposes pre-computed relational edges containing:
   - `parent_table: str`
   - `child_table: str`
   - `cardinality_symbol: str` (e.g., `||--o{`, `||--||`, `||--|{`, inferred from FK nullability and uniqueness if not explicitly declared)
   - `label: str` (relationship label or business verb)
4. **No Direct Dict Parsing**:
   `core/diagram.py` works exclusively against typed `DataContract` objects without raw dict key navigation or manual string splitting.

### 2.3 Consumer 3: `core/exporter.py` (M4 — Deliverables & Multi-Format Exporter)

#### Role & Interaction
Upon Pytest sandbox validation (return code 0), `core/exporter.py` writes standalone deliverables (`output/generator.py`, `output/test_mock.py`, and CSV/JSON/Parquet files in `output/datasets/`).

#### Guarantees Provided by `core/contract_parser.py`:
1. **DAG Dependency Sequence**:
   Standalone `generator.py` must define generation functions sorted topographically (`contract.get_dag_order()`), ensuring parent dataframes are available in child generation calls.
2. **Column Presence & Order**:
   `table.field_names -> List[str]` allows `exporter.py` to assert that simulated dataframes match the exact contract column set before writing to disk.
3. **Table Sample Sizes**:
   `table.sample_size` and `contract.default_sample_size` provide default row generation targets per entity.

### 2.4 Consumer 4: `cli/main.py` (M5 — Interactive CLI Typer/Rich)

#### Role & Interaction
- `simula inspect <contract_path>`: renders Rich tree and tables of tables, columns, constraints, and DAG order.
- `simula run <contract_path>`: pre-validates contract before starting the cognitive loop.
- `simula diagram <contract_path>`: generates and displays Mermaid ER diagrams.

#### Guarantees Provided by `core/contract_parser.py`:
1. **Field Constraint Summaries**:
   `field.constraints_summary() -> str` produces human-readable tags (e.g., `"PK, NOT NULL, unique, regex=^\\d{2}..."`) for Rich tables.
2. **Explicit Error Messages with File Locations**:
   `ContractError` subclasses provide structured `.message` and context attributes so the CLI renders high-visibility Red Panels without raw Python stack traces.
3. **Contract Metadata**:
   Accessors for `contract.mesh_name`, `contract.version`, `contract.domain`, and `contract.description`.

### 2.5 Consumer 5: `ui/app.py` (M5 — Streamlit Web UI)

#### Role & Interaction
Streamlit UI provides an interactive contract studio with YAML editor, live validation badge, and dynamic Mermaid rendering.

#### Guarantees Provided by `core/contract_parser.py`:
1. **In-Memory Parsing**:
   `parse_contract_from_string(yaml_str: str) -> DataContract` allows live validation directly from `st.text_area` or `st.file_uploader`.
2. **Non-Throwing Safe Parser**:
   `safe_parse_contract(yaml_str: str) -> Tuple[Optional[DataContract], Optional[str]]` returns `(contract, None)` or `(None, error_str)` so Streamlit displays a validation banner instead of throwing uncaught exceptions.
3. **Session State Serialization**:
   `contract.to_dict()` and `contract.to_yaml()` support caching in `st.session_state`.

---

## 3. Concrete Architecture & Method Signatures of `core/contract_parser.py`

### 3.1 Exception Hierarchy

```python
class ContractError(Exception):
    """Base exception for all contract parsing and validation errors."""
    pass

class ContractFileNotFoundError(ContractError):
    """Raised when the specified contract YAML file does not exist."""
    pass

class ContractParseError(ContractError):
    """Raised when the contract YAML syntax is invalid."""
    pass

class ContractValidationError(ContractError):
    """Raised when contract schema fails Pydantic validation or domain rules."""
    pass

class CircularDependencyError(ContractValidationError):
    """Raised when foreign key relationships contain cyclic dependencies."""
    pass

class InvalidForeignKeyError(ContractValidationError):
    """Raised when a foreign key references a non-existent table or column."""
    pass
```

### 3.2 Data Models Specification (Pydantic v2)

```python
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from pydantic import BaseModel, Field, model_validator


class ForeignKeyContract(BaseModel):
    """Foreign key relationship definition."""
    field: str = Field(description="Name of the child column referencing parent.")
    references_table: str = Field(description="Target parent table name.")
    references_field: str = Field(description="Target parent column name.")
    relationship_type: Optional[str] = Field(
        default=None,
        description="Semantic cardinality: many_to_one, one_to_one, one_to_many, many_to_many."
    )
    cardinality: Optional[str] = Field(
        default=None,
        description="Mermaid cardinality symbol: ||--o{, ||--||, etc."
    )
    relationship_name: Optional[str] = Field(
        default=None,
        description="Semantic verb or relationship label (e.g. submete, possui)."
    )
    filter_condition: Optional[str] = Field(
        default=None,
        description="Domain filter condition (e.g. status == 'APROVADA')."
    )

    @property
    def target_reference(self) -> str:
        """Normalized string representation: 'table.field'."""
        return f"{self.references_table}.{self.references_field}"


class FieldContract(BaseModel):
    """Field specification with constraints and immutable accessors."""
    name: str
    type: str
    format: Optional[str] = None
    faker: Optional[str] = None
    nullable: bool = False
    primary_key: bool = False
    unique: bool = False
    foreign_key: Optional[str] = None  # Format: "table.field"
    regex: Optional[str] = None
    min_value: Optional[Union[int, float, str]] = None
    max_value: Optional[Union[int, float, str]] = None
    enum_values: List[Any] = Field(default_factory=list)
    description: Optional[str] = None
    rules: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def flatten_nested_constraints(cls, data: Any) -> Any:
        """Flatten nested 'constraints' dict from YAML schema if present."""
        if not isinstance(data, dict):
            return data
        
        constraints = data.get("constraints")
        if isinstance(constraints, dict):
            # Unpack constraints without overriding explicit top-level values
            for key in ["primary_key", "nullable", "unique", "foreign_key", "regex", "format"]:
                if key in constraints and key not in data:
                    data[key] = constraints[key]
            
            # Map numeric/date bounds
            if "min" in constraints and "min_value" not in data:
                data["min_value"] = constraints["min"]
            if "max" in constraints and "max_value" not in data:
                data["max_value"] = constraints["max"]
            
            # Map enum list
            if "enum" in constraints and "enum_values" not in data:
                data["enum_values"] = constraints["enum"]
        
        return data

    @property
    def is_pk(self) -> bool:
        return bool(self.primary_key)

    @property
    def is_fk(self) -> bool:
        return bool(self.foreign_key)

    @property
    def is_uk(self) -> bool:
        return bool(self.unique and not self.primary_key)

    @property
    def fk_target_table(self) -> Optional[str]:
        if self.foreign_key and "." in self.foreign_key:
            return self.foreign_key.split(".", 1)[0]
        return None

    @property
    def fk_target_field(self) -> Optional[str]:
        if self.foreign_key and "." in self.foreign_key:
            return self.foreign_key.split(".", 1)[1]
        return None

    @property
    def sanitized_mermaid_type(self) -> str:
        """Strip parameters like (255) and illegal characters for Mermaid erDiagram."""
        cleaned = re.sub(r'\(.*?\)', '', str(self.type).strip())
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned)
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
            tokens.append(f"REGEX")
        if self.min_value is not None or self.max_value is not None:
            tokens.append(f"RANGE[{self.min_value}..{self.max_value}]")
        return ", ".join(tokens) or "NONE"


class TableContract(BaseModel):
    """Table contract specification."""
    name: str
    description: Optional[str] = None
    primary_key: Union[str, List[str]] = Field(default_factory=list)
    sample_size: int = 100
    fields: List[FieldContract] = Field(default_factory=list)
    foreign_keys: List[ForeignKeyContract] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def harmonize_keys_and_fields(self) -> TableContract:
        """Normalize primary keys and foreign keys bidirectionally."""
        # 1. Normalize primary key to list
        if isinstance(self.primary_key, str):
            pks = [self.primary_key] if self.primary_key else []
        else:
            pks = list(self.primary_key)
        
        # Mark fields with primary_key=True if present in pks list
        for f in self.fields:
            if f.name in pks:
                f.primary_key = True
            elif f.primary_key and f.name not in pks:
                pks.append(f.name)
        self.primary_key = pks

        # 2. Synchronize field.foreign_key with table.foreign_keys
        existing_fk_fields = {fk.field for fk in self.foreign_keys}
        
        # Pull foreign_keys from fields into table.foreign_keys if not present
        for f in self.fields:
            if f.foreign_key and f.name not in existing_fk_fields:
                parts = f.foreign_key.split(".", 1)
                if len(parts) == 2:
                    self.foreign_keys.append(
                        ForeignKeyContract(
                            field=f.name,
                            references_table=parts[0],
                            references_field=parts[1]
                        )
                    )
        
        # Push table.foreign_keys back into field.foreign_key if missing
        fk_map = {fk.field: fk.target_reference for fk in self.foreign_keys}
        for f in self.fields:
            if f.name in fk_map and not f.foreign_key:
                f.foreign_key = fk_map[f.name]

        return self

    def get_field(self, name: str) -> Optional[FieldContract]:
        for field in self.fields:
            if field.name.lower() == name.lower():
                return field
        return None

    @property
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    @property
    def primary_key_fields(self) -> List[str]:
        return [f.name for f in self.fields if f.primary_key]

    @property
    def foreign_key_fields(self) -> List[FieldContract]:
        return [f for f in self.fields if f.foreign_key]

    @property
    def referenced_tables(self) -> Set[str]:
        return {fk.references_table for fk in self.foreign_keys}


class RelationshipContract(BaseModel):
    """Immutable representation of a directed relationship edge between two entities."""
    parent_table: str
    parent_field: str
    child_table: str
    child_field: str
    relationship_type: str
    cardinality_symbol: str
    label: str
    filter_condition: Optional[str] = None


class DataContract(BaseModel):
    """Root data contract model."""
    data_contract_version: str = Field(default="1.0.0")
    domain: str = Field(default="default")
    dataset_name: str = Field(default="default_mesh")
    description: Optional[str] = None
    owner: Optional[str] = None
    locale: str = Field(default="pt_BR")
    default_sample_size: int = Field(default=100)
    tables: List[TableContract] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list)

    # Aliases for PROJECT.md backward-compatibility
    @property
    def mesh_name(self) -> str:
        return self.dataset_name

    @property
    def version(self) -> str:
        return self.data_contract_version

    @model_validator(mode="before")
    @classmethod
    def harmonize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "mesh_name" in data and "dataset_name" not in data:
                data["dataset_name"] = data["mesh_name"]
            if "version" in data and "data_contract_version" not in data:
                data["data_contract_version"] = data["version"]
        return data

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> DataContract:
        """Assert that all foreign keys reference existing tables and columns."""
        table_map = {t.name: t for t in self.tables}
        
        for table in self.tables:
            for fk in table.foreign_keys:
                if fk.references_table not in table_map:
                    raise InvalidForeignKeyError(
                        f"Table '{table.name}' foreign key '{fk.field}' references non-existent table '{fk.references_table}'."
                    )
                parent_table = table_map[fk.references_table]
                parent_field = parent_table.get_field(fk.references_field)
                if not parent_field:
                    raise InvalidForeignKeyError(
                        f"Table '{table.name}' foreign key '{fk.field}' references non-existent column '{fk.references_field}' on table '{fk.references_table}'."
                    )
        return self

    def get_table(self, name: str) -> Optional[TableContract]:
        for table in self.tables:
            if table.name.lower() == name.lower():
                return table
        return None

    @property
    def table_names(self) -> List[str]:
        return [t.name for t in self.tables]

    def get_dag_order(self) -> List[str]:
        """
        Calculates topological sort order of tables using Kahn's algorithm.
        Parent tables (referenced by FKs) are ordered before child tables.
        Raises CircularDependencyError if cyclic dependencies exist.
        """
        # Graph construction
        in_degree: Dict[str, int] = {t.name: 0 for t in self.tables}
        dependents: Dict[str, Set[str]] = {t.name: set() for t in self.tables}

        for table in self.tables:
            for ref_table in table.referenced_tables:
                if ref_table != table.name and ref_table in in_degree:
                    # ref_table -> table
                    if table.name not in dependents[ref_table]:
                        dependents[ref_table].add(table.name)
                        in_degree[table.name] += 1

        # Kahn's queue: tables with in_degree 0
        queue = [t.name for t in self.tables if in_degree[t.name] == 0]
        sorted_order: List[str] = []

        while queue:
            current = queue.pop(0)
            sorted_order.append(current)
            for child in sorted(dependents[current]):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(sorted_order) != len(self.tables):
            unresolved = [t.name for t in self.tables if in_degree[t.name] > 0]
            raise CircularDependencyError(
                f"Circular foreign key dependency detected among tables: {unresolved}"
            )

        return sorted_order

    def get_relationships(self) -> List[RelationshipContract]:
        """Extracts complete relationship list with inferred Mermaid cardinalities."""
        relationships: List[RelationshipContract] = []
        table_map = {t.name: t for t in self.tables}

        for table in self.tables:
            for fk in table.foreign_keys:
                parent_table = table_map.get(fk.references_table)
                child_field = table.get_field(fk.field)
                
                # Inferred cardinality heuristic
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
                        filter_condition=fk.filter_condition
                    )
                )
        return relationships

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def to_yaml(self) -> str:
        import yaml
        return yaml.dump(self.model_dump(), sort_keys=False, allow_unicode=True)

    def to_prompt_context(self) -> str:
        """Generates a dense markdown schema summary for LLM prompt context injection."""
        lines = [
            f"# Data Mesh Contract: {self.dataset_name} (v{self.data_contract_version})",
            f"Domain: {self.domain} | Locale: {self.locale}",
            "",
            "## Table Generation Order (Topological DAG):",
            " -> ".join(self.get_dag_order()),
            "",
            "## Tables & Schema:"
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
                    lines.append(f"  - {rule}")
            lines.append("")
        return "\n".join(lines)
```

---

## 4. Top-Level Utility Functions Specification

```python
from pathlib import Path
from typing import Tuple, Union
import yaml


def load_contract(file_path: Union[str, Path]) -> DataContract:
    """
    Loads and validates a contract YAML file from disk.
    
    Raises:
        ContractFileNotFoundError: If the file does not exist.
        ContractParseError: If YAML syntax is invalid.
        ContractValidationError: If schema validation fails.
    """
    path = Path(file_path)
    if not path.is_file():
        raise ContractFileNotFoundError(f"Contract file not found at '{path.resolve()}'.")
    
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise ContractError(f"Failed to read file '{path}': {e}") from e

    return parse_contract_from_string(content)


def parse_contract(source: Union[str, Path]) -> DataContract:
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
        ContractValidationError: If schema validation fails.
    """
    if not yaml_content or not yaml_content.strip():
        raise ContractValidationError("Contract YAML content is empty.")

    try:
        parsed_data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ContractParseError(f"Invalid YAML syntax: {e}") from e

    if not isinstance(parsed_data, dict):
        raise ContractValidationError(f"Expected YAML mapping at root, got {type(parsed_data).__name__}.")

    try:
        return DataContract(**parsed_data)
    except (CircularDependencyError, InvalidForeignKeyError):
        raise
    except Exception as e:
        raise ContractValidationError(f"Contract schema validation error: {e}") from e


def safe_parse_contract(source: Union[str, Path]) -> Tuple[Optional[DataContract], Optional[str]]:
    """
    Non-throwing safe parsing utility for UI and interactive CLI flows.
    Returns (DataContract, None) on success or (None, error_message) on failure.
    """
    try:
        contract = parse_contract(source)
        return contract, None
    except Exception as e:
        return None, str(e)
```

---

## 5. Topological DAG Resolution & Kahn's Algorithm Analysis

### 5.1 Kahn's Algorithm Trace on `exemplo_credito_mesh.yaml`
In the sample credit mesh:
- Table `empresas`: `referenced_tables = {}` -> `in_degree = 0`
- Table `propostas`: `referenced_tables = {"empresas"}` -> `in_degree = 1`
- Table `garantias`: `referenced_tables = {"propostas"}` -> `in_degree = 1`
- Table `operacoes`: `referenced_tables = {"propostas", "empresas"}` -> `in_degree = 2`

**Step-by-step execution**:
1. Initial queue with in-degree 0: `["empresas"]`
2. Pop `empresas`:
   - Sorted list: `["empresas"]`
   - Decrement dependents:
     - `propostas`: in-degree becomes 0 -> Enqueue `propostas`
     - `operacoes`: in-degree becomes 1 (still waiting on `propostas`)
3. Pop `propostas`:
   - Sorted list: `["empresas", "propostas"]`
   - Decrement dependents:
     - `garantias`: in-degree becomes 0 -> Enqueue `garantias`
     - `operacoes`: in-degree becomes 0 -> Enqueue `operacoes`
4. Pop `garantias`:
   - Sorted list: `["empresas", "propostas", "garantias"]`
5. Pop `operacoes`:
   - Sorted list: `["empresas", "propostas", "garantias", "operacoes"]`
6. Output: 4 tables resolved. 4 == len(tables) -> **Valid DAG**.

### 5.2 Cyclic Edge Cases
If table A references table B and table B references table A:
- `in_degree["A"] = 1`, `in_degree["B"] = 1`.
- Queue is empty (`[]`).
- Sorted order length 0 != 2 -> Raises `CircularDependencyError: Circular foreign key dependency detected among tables: ['A', 'B']`.

---

## 6. Implementation Blueprint & Worker Dispatch Instructions for Milestone 1 Worker

### 6.1 Artifacts to Author

| File | Purpose | Key Contents |
|---|---|---|
| `contracts/exemplo_credito_mesh.yaml` | Reference credit mesh schema | 4 tables (`empresas`, `propostas`, `garantias`, `operacoes`), PK/FKs, regex, rules |
| `core/__init__.py` | Package export entrypoint | Export `DataContract`, `TableContract`, `FieldContract`, `load_contract`, `parse_contract` |
| `core/contract_parser.py` | Complete parser & models | Pydantic v2 classes, Kahn's algorithm, custom exceptions, helpers |
| `pyproject.toml` | Build & project metadata | PEP 621 configuration, dependencies, CLI entrypoint `simula = "cli.main:app"` |
| `requirements.txt` | Pinned runtime dependencies | Pinned core libraries (`pydantic>=2.7`, `pyyaml>=6.0`, `typer`, `rich`, etc.) |
| `.env.example` | Environment configuration template | OpenRouter credentials, model options, sandbox timeouts |
| `tests/__init__.py` | Test package marker | Empty |
| `tests/unit/__init__.py` | Unit test package marker | Empty |
| `tests/unit/test_contract_parser.py` | Unit test suite | 100% test coverage for valid loading, accessors, DAG order, and error cases |

### 6.2 Unit Test Verification Matrix (`tests/unit/test_contract_parser.py`)

The worker must implement the following tests:
1. `test_load_valid_credit_mesh_contract`: Verifies loading of `contracts/exemplo_credito_mesh.yaml`, checking 4 tables, proper domain, version, and metadata.
2. `test_table_and_field_accessors`: Tests `contract.get_table()`, `table.get_field()`, `field.is_pk`, `field.is_fk`, `field.sanitized_mermaid_type`.
3. `test_topological_dag_order`: Asserts `contract.get_dag_order()` returns `['empresas', 'propostas', ...]` with `empresas` before `propostas` and `propostas` before `garantias`/`operacoes`.
4. `test_circular_dependency_detection`: Injects cyclic FKs (`table_a -> table_b -> table_a`) and asserts `pytest.raises(CircularDependencyError)`.
5. `test_missing_file_error`: Tests `load_contract("non_existent.yaml")` raises `ContractFileNotFoundError`.
6. `test_malformed_yaml_error`: Tests broken YAML string raises `ContractParseError`.
7. `test_invalid_foreign_key_target`: Tests FK pointing to non-existent table or field raises `InvalidForeignKeyError`.
8. `test_empty_yaml_error`: Tests empty string raises `ContractValidationError`.
9. `test_safe_parse_contract`: Tests `safe_parse_contract()` returns tuple without throwing.
10. `test_to_prompt_context`: Tests that `contract.to_prompt_context()` generates non-empty markdown containing table and column names.

### 6.3 Worker Execution Verification Command
```bash
pytest tests/unit/test_contract_parser.py -v
```
Gate: 100% pass, zero errors or warnings.
