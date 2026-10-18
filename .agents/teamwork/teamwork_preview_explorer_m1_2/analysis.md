# Technical Analysis: Packaging, Dependencies, Environment Setup & Contract Parser Test Suite (Milestone 1)

**Agent:** Explorer 2 (Milestone 1 - Contract Specification & Foundation)  
**Date:** 2026-10-12  
**Target Project:** Simula-AI  
**Scope:** Packaging (`pyproject.toml`, `requirements.txt`), Environment Configuration (`.env.example`), and Unit Testing Suite (`tests/unit/test_contract_parser.py`)

---

## 1. Executive Summary & Environmental Baseline

Simula-AI requires a unified, modern packaging setup compatible across Python 3.12, 3.13, and 3.14, with zero friction during local development, containerized builds (Podman), and CI/CD pipelines.

### Environmental Baseline Verified
- **Host Runtime:** Python 3.14.4 on macOS (Darwin arm64).
- **Installed Base in Site-Packages:** `pytest 9.1.1`, `pandas 3.0.5`, `numpy 2.5.1`, `ruff 0.16.8`.
- **Dry-run Resolution Verification:** Executed `pip install --dry-run` against target pins. All 12 key dependencies and their transitive wheels resolve without C/Rust compilation errors on Python 3.14:
  - `pydantic-2.14.1` with `pydantic-core==2.50.1` (cp314 wheel)
  - `pyyaml-6.0.3` (cp314 wheel)
  - `pyarrow-25.0.1` (cp314 wheel)
  - `langgraph-1.2.15` (pure Python wheel, with cp314 wheels for `xxhash`, `orjson`, `ormsgpack`)
  - `streamlit-1.65.0` (pure Python wheel, with cp314 wheels for `rpds-py`, `markupsafe`, `websockets`)
  - `typer-0.27.3`, `rich-15.0.0`, `faker-40.43.0`, `httpx-0.28.1`, `python-dotenv-1.2.4`.

---

## 2. Packaging Specification: `pyproject.toml` and `requirements.txt`

### 2.1 Dependency Pins & Justification

| Dependency | Minimum Pin | Justification & Python 3.12-3.14 Compatibility |
|---|---|---|
| `pydantic` | `>=2.7.0` | Core schema validation for data contracts and state models. Pre-compiled `pydantic-core` wheels available for Python 3.12, 3.13, and 3.14. |
| `pyyaml` | `>=6.0` | Contract YAML parsing. Note: PyYAML 6.0.1+ is required on Python 3.12+ to avoid Cython build deprecation errors; pip resolves to 6.0.3 on 3.14. |
| `typer` | `>=0.12.0` | CLI command parser with automatic help generation and subcommands. Pure Python, fully compatible with 3.12-3.14. |
| `rich` | `>=13.7.0` | Terminal rendering (spinners, panels, tree viewers, syntax highlighting). Pure Python. |
| `streamlit` | `>=1.35.0` | Web UI interactive dashboard. Pure Python frontend framework with pre-built transitive binary dependencies. |
| `faker` | `>=25.0.0` | Relational mock data generator engine (names, companies, CNPJ, dates, UUIDs). Pure Python. |
| `pandas` | `>=2.2.0` | Tabular data manipulation, formatting, and intermediate test verification. Pre-built wheels for 3.12, 3.13, and 3.14 (supports 3.0+). |
| `pyarrow` | `>=16.0.0` | High-performance Parquet dataset export. Pre-compiled binary wheels available across 3.12, 3.13, and 3.14. |
| `langgraph` | `>=0.0.60` | StateGraph execution for CoALA cognitive loop. Pure Python orchestration layer; resolves cleanly to modern versions (0.2+ / 1.2+). |
| `httpx` | `>=0.27.0` | Asynchronous/synchronous HTTP client for OpenRouter API with backoff handling. Pure Python. |
| `pytest` | `>=8.0.0` | Test runner and sandbox test verification engine. Pure Python. |
| `python-dotenv` | `>=1.0.0` | Environment variable loader from `.env` files. Pure Python. |

### 2.2 Complete `pyproject.toml` Specification

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "simula-ai"
version = "0.1.0"
description = "Autonomous relational data mocking framework for Data Mesh ecosystems"
readme = "README.md"
requires-python = ">=3.12"
authors = [
    { name = "Simula-AI Team" }
]
license = { text = "MIT" }
dependencies = [
    "pydantic>=2.7.0",
    "pyyaml>=6.0",
    "typer>=0.12.0",
    "rich>=13.7.0",
    "streamlit>=1.35.0",
    "faker>=25.0.0",
    "pandas>=2.2.0",
    "pyarrow>=16.0.0",
    "langgraph>=0.0.60",
    "httpx>=0.27.0",
    "pytest>=8.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.4.0",
]

[project.scripts]
simula = "cli.main:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N"]
ignore = ["E501"]
```

### 2.3 Complete `requirements.txt` Specification

```text
# Simula-AI Pinned Dependencies (Python 3.12-3.14 Compatible)
pydantic>=2.7.0
pyyaml>=6.0
typer>=0.12.0
rich>=13.7.0
streamlit>=1.35.0
faker>=25.0.0
pandas>=2.2.0
pyarrow>=16.0.0
langgraph>=0.0.60
httpx>=0.27.0
pytest>=8.0.0
python-dotenv>=1.0.0
```

---

## 3. Environment Setup & Configuration: `.env.example`

### 3.1 Required Variables Matrix

| Variable | Type | Default in `.env.example` | Purpose & Operational Impact |
|---|---|---|---|
| `OPENROUTER_API_KEY` | `string` | `your_openrouter_api_key_here` | Authentication token for OpenRouter (`https://openrouter.ai/api/v1`). Required in live mode; ignored if `SIMULA_MOCK_LLM=true`. |
| `OPENROUTER_BASE_URL` | `string` | `https://openrouter.ai/api/v1` | Base URL for LLM completions. Allows routing to local proxies or mock gateways. |
| `OPENROUTER_MODEL` | `string` | `deepseek/deepseek-r1` | Primary LLM model. Reasoning model capable of complex relational schema synthesis. |
| `SIMULA_MOCK_LLM` | `boolean` | `false` | When `true`, activates offline deterministic test double in `core/llm_client.py`. Used in CI/CD and E2E testing without incurring token costs or network latency. |
| `SIMULA_MAX_ITERATIONS` | `integer` | `5` | Maximum number of reflection loops in LangGraph StateGraph before terminating with `FAILED_MAX_RETRIES`. |
| `SIMULA_TIMEOUT` | `integer` | `30` | Maximum timeout in seconds for Pytest sandbox subprocess (`simula_temp_test.py`). Protects against infinite loops in synthetic generator scripts. |

### 3.2 Complete `.env.example` Content

```bash
# ==============================================================================
# Simula-AI Configuration Template
# Copy this file to .env and configure your values:
#   cp .env.example .env
# ==============================================================================

# --- OpenRouter API Configuration ---
# Your OpenRouter API key (sk-or-v1-...)
# Obtain from https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key_here

# OpenRouter Base API URL (default: https://openrouter.ai/api/v1)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Primary Reasoning Model for synthetic code & test generation
# Recommended: deepseek/deepseek-r1
# Alternatives: deepseek/deepseek-chat, deepseek/deepseek-r1-distill-llama-70b
OPENROUTER_MODEL=deepseek/deepseek-r1

# --- Cognitive Loop & Sandbox Controls ---
# Enable Mock LLM for deterministic offline testing and CI (true/false)
# When true, no network calls to OpenRouter are made.
SIMULA_MOCK_LLM=false

# Maximum retry loops when Pytest sandbox assertions fail (default: 5)
SIMULA_MAX_ITERATIONS=5

# Subprocess Pytest execution sandbox timeout in seconds (default: 30)
SIMULA_TIMEOUT=30
```

### 3.3 Configuration Loader Pattern (`core/config.py`)

To ensure consistent ingestion of `.env` across CLI, Streamlit UI, and core engine:

```python
"""core/config.py - Centralized configuration loader for Simula-AI."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class SimulaConfig:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1")
    mock_llm: bool = os.getenv("SIMULA_MOCK_LLM", "false").lower() in ("true", "1", "yes")
    max_iterations: int = int(os.getenv("SIMULA_MAX_ITERATIONS", "5"))
    timeout: int = int(os.getenv("SIMULA_TIMEOUT", "30"))

config = SimulaConfig()
```

---

## 4. Unit Testing Setup: `tests/unit/test_contract_parser.py`

### 4.1 Test Scope & Coverage Architecture

The test suite for `core/contract_parser.py` must exhaustively validate:
1. **Valid Contracts:** Loading full credit mesh schema, verifying fields, types, constraints, PKs, FKs, and DAG order.
2. **Missing Tables & Fields:** Empty table lists, tables without primary keys, tables without fields, duplicate table/field names.
3. **Invalid Foreign Keys:** Non-existent target table, non-existent target field, malformed format string (not `table.field`), nullable PK violation.
4. **DAG Cycle Detection:** 2-table circular dependencies (A -> B -> A), 3-table transitive cycles (A -> B -> C -> A), disconnected subgraphs containing cycles, cycle diagnostics in exception messages.
5. **Topological Generation Order:** Correct ordering where parent tables precede child tables, determinism across multiple runs.
6. **I/O & Serialization:** Parsing from YAML string, parsing from file `Path`, `FileNotFoundError` on invalid path, serialization to YAML.

### 4.2 Complete `tests/unit/test_contract_parser.py` Implementation

Below is the complete, self-contained unit test file for `tests/unit/test_contract_parser.py`:

```python
"""tests/unit/test_contract_parser.py - Comprehensive Unit Tests for DataContract Parser."""

import pytest
from pathlib import Path
from typing import List

from core.contract_parser import (
    DataContract,
    TableContract,
    FieldContract,
    ForeignKeyDefinition,
    DataContractError,
    ContractParseError,
    DataContractValidationError,
    DuplicateTableError,
    DuplicateFieldError,
    MissingTableError,
    MissingFieldError,
    MissingPrimaryKeyError,
    InvalidForeignKeyError,
    CyclicDependencyError,
)

# --- Fixtures ---

@pytest.fixture
def valid_credit_mesh_yaml() -> str:
    """Fixture providing full 4-table credit mesh schema."""
    return """
data_contract_version: "1.0.0"
domain: "credit_risk"
dataset_name: "credit_mesh_ecosystem"
description: "Data Contract for corporate credit mesh"
tables:
  - name: "empresas"
    primary_key: "empresa_id"
    sample_size: 100
    fields:
      - name: "empresa_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
          unique: true
      - name: "cnpj"
        type: "string"
        constraints:
          nullable: false
          unique: true
      - name: "razao_social"
        type: "string"
      - name: "faturamento_anual"
        type: "decimal"

  - name: "propostas"
    primary_key: "proposta_id"
    sample_size: 150
    foreign_keys:
      - field: "empresa_id"
        references_table: "empresas"
        references_field: "empresa_id"
        relationship_type: "many_to_one"
    fields:
      - name: "proposta_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas.empresa_id"
      - name: "valor_solicitado"
        type: "decimal"

  - name: "garantias"
    primary_key: "garantia_id"
    sample_size: 180
    foreign_keys:
      - field: "proposta_id"
        references_table: "propostas"
        references_field: "proposta_id"
        relationship_type: "many_to_one"
    fields:
      - name: "garantia_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "proposta_id"
        type: "string"
        foreign_key: "propostas.proposta_id"
      - name: "valor_avaliado"
        type: "decimal"

  - name: "operacoes"
    primary_key: "operacao_id"
    sample_size: 90
    foreign_keys:
      - field: "proposta_id"
        references_table: "propostas"
        references_field: "proposta_id"
        relationship_type: "one_to_one"
      - field: "empresa_id"
        references_table: "empresas"
        references_field: "empresa_id"
        relationship_type: "many_to_one"
    fields:
      - name: "operacao_id"
        type: "string"
        constraints:
          primary_key: true
          nullable: false
      - name: "proposta_id"
        type: "string"
        foreign_key: "propostas.proposta_id"
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas.empresa_id"
      - name: "valor_contratado"
        type: "decimal"
"""


# ==============================================================================
# 1. Valid Contracts Test Suite
# ==============================================================================

class TestValidContracts:
    def test_parse_valid_credit_mesh(self, valid_credit_mesh_yaml: str):
        contract = DataContract.from_yaml(valid_credit_mesh_yaml)
        assert contract.mesh_name == "credit_mesh_ecosystem"
        assert contract.version == "1.0.0"
        assert len(contract.tables) == 4
        assert contract.get_table_names() == ["empresas", "propostas", "garantias", "operacoes"]

    def test_table_and_field_lookup(self, valid_credit_mesh_yaml: str):
        contract = DataContract.from_yaml(valid_credit_mesh_yaml)
        tbl = contract.get_table("empresas")
        assert tbl is not None
        assert tbl.name == "empresas"
        assert tbl.get_primary_keys() == ["empresa_id"]

        field = tbl.get_field("cnpj")
        assert field is not None
        assert field.name == "cnpj"
        assert field.type == "string"
        assert field.unique is True

        # Non-existent table
        assert contract.get_table("tabela_fantasma") is None
        # Non-existent field
        assert tbl.get_field("campo_fantasma") is None

    def test_composite_primary_key(self):
        yaml_content = """
mesh_name: "composite_mesh"
tables:
  - name: "order_items"
    primary_key: ["order_id", "item_id"]
    fields:
      - name: "order_id"
        type: "string"
      - name: "item_id"
        type: "integer"
      - name: "quantity"
        type: "integer"
"""
        contract = DataContract.from_yaml(yaml_content)
        tbl = contract.get_table("order_items")
        assert tbl is not None
        assert tbl.get_primary_keys() == ["order_id", "item_id"]
        assert tbl.get_field("order_id").primary_key is True
        assert tbl.get_field("item_id").primary_key is True

    def test_self_referencing_foreign_key(self):
        yaml_content = """
mesh_name: "self_ref_mesh"
tables:
  - name: "employees"
    primary_key: "emp_id"
    fields:
      - name: "emp_id"
        type: "string"
      - name: "manager_id"
        type: "string"
        nullable: true
        foreign_key: "employees.emp_id"
"""
        contract = DataContract.from_yaml(yaml_content)
        order = contract.get_dag_order()
        assert order == ["employees"]

    def test_from_yaml_file_path(self, tmp_path: Path, valid_credit_mesh_yaml: str):
        yaml_file = tmp_path / "test_mesh.yaml"
        yaml_file.write_text(valid_credit_mesh_yaml, encoding="utf-8")
        
        contract = DataContract.from_yaml(yaml_file)
        assert contract.mesh_name == "credit_mesh_ecosystem"
        assert len(contract.tables) == 4


# ==============================================================================
# 2. Missing Tables & Schema Validation Errors Test Suite
# ==============================================================================

class TestMissingTablesAndSchemaErrors:
    def test_empty_tables_list(self):
        yaml_content = """
mesh_name: "empty_mesh"
tables: []
"""
        with pytest.raises(DataContractValidationError, match="at least one table"):
            DataContract.from_yaml(yaml_content)

    def test_table_without_fields(self):
        yaml_content = """
mesh_name: "no_fields_mesh"
tables:
  - name: "tbl"
    primary_key: "id"
    fields: []
"""
        with pytest.raises(Exception):
            DataContract.from_yaml(yaml_content)

    def test_missing_primary_key_field(self):
        yaml_content = """
mesh_name: "bad_pk_mesh"
tables:
  - name: "tbl"
    primary_key: "non_existent_pk"
    fields:
      - name: "col1"
        type: "string"
"""
        with pytest.raises(MissingPrimaryKeyError, match="not found in fields"):
            DataContract.from_yaml(yaml_content)

    def test_duplicate_tables(self):
        yaml_content = """
mesh_name: "dup_tables_mesh"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
"""
        with pytest.raises(DuplicateTableError, match="Duplicate tables"):
            DataContract.from_yaml(yaml_content)

    def test_duplicate_fields(self):
        yaml_content = """
mesh_name: "dup_fields_mesh"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
      - name: "id"
        type: "integer"
"""
        with pytest.raises(DuplicateFieldError, match="Duplicate fields"):
            DataContract.from_yaml(yaml_content)

    def test_nullable_primary_key_rejected(self):
        yaml_content = """
mesh_name: "nullable_pk_mesh"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
        nullable: true
"""
        with pytest.raises(DataContractValidationError, match="cannot be nullable"):
            DataContract.from_yaml(yaml_content)


# ==============================================================================
# 3. Invalid Foreign Keys Test Suite
# ==============================================================================

class TestInvalidForeignKeys:
    def test_fk_references_missing_table(self):
        yaml_content = """
mesh_name: "missing_parent_mesh"
tables:
  - name: "propostas"
    primary_key: "proposta_id"
    fields:
      - name: "proposta_id"
        type: "string"
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas_fantasma.empresa_id"
"""
        with pytest.raises(MissingTableError, match="references unknown table 'empresas_fantasma'"):
            DataContract.from_yaml(yaml_content)

    def test_fk_references_missing_field(self):
        yaml_content = """
mesh_name: "missing_parent_field_mesh"
tables:
  - name: "empresas"
    primary_key: "empresa_id"
    fields:
      - name: "empresa_id"
        type: "string"
  - name: "propostas"
    primary_key: "proposta_id"
    fields:
      - name: "proposta_id"
        type: "string"
      - name: "empresa_id"
        type: "string"
        foreign_key: "empresas.campo_inexistente"
"""
        with pytest.raises(MissingFieldError, match="references non-existent field 'campo_inexistente'"):
            DataContract.from_yaml(yaml_content)

    def test_fk_malformed_string_format(self):
        yaml_content = """
mesh_name: "malformed_fk_mesh"
tables:
  - name: "tbl"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
      - name: "fk_col"
        type: "string"
        foreign_key: "sem_ponto_separador"
"""
        with pytest.raises(InvalidForeignKeyError, match="Expected 'table.field'"):
            DataContract.from_yaml(yaml_content)


# ==============================================================================
# 4. DAG Cycle Detection Test Suite
# ==============================================================================

class TestDAGCycleDetection:
    def test_cycle_direct_2_tables(self):
        yaml_content = """
mesh_name: "cycle_2_mesh"
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
        with pytest.raises(CyclicDependencyError, match="Circular foreign key dependency detected"):
            DataContract.from_yaml(yaml_content)

    def test_cycle_transitive_3_tables(self):
        yaml_content = """
mesh_name: "cycle_3_mesh"
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
      - name: "id_c"
        type: "string"
        foreign_key: "table_c.id_c"
  - name: "table_c"
    primary_key: "id_c"
    fields:
      - name: "id_c"
        type: "string"
      - name: "id_a"
        type: "string"
        foreign_key: "table_a.id_a"
"""
        with pytest.raises(CyclicDependencyError) as exc_info:
            DataContract.from_yaml(yaml_content)
        assert "Circular foreign key dependency detected" in str(exc_info.value)
        assert "table_a" in str(exc_info.value)
        assert "table_b" in str(exc_info.value)
        assert "table_c" in str(exc_info.value)

    def test_cycle_in_disconnected_subgraph(self):
        yaml_content = """
mesh_name: "partial_cycle_mesh"
tables:
  - name: "valid_root"
    primary_key: "id"
    fields:
      - name: "id"
        type: "string"
  - name: "cycle_x"
    primary_key: "id_x"
    fields:
      - name: "id_x"
        type: "string"
      - name: "id_y"
        type: "string"
        foreign_key: "cycle_y.id_y"
  - name: "cycle_y"
    primary_key: "id_y"
    fields:
      - name: "id_y"
        type: "string"
      - name: "id_x"
        type: "string"
        foreign_key: "cycle_x.id_x"
"""
        with pytest.raises(CyclicDependencyError):
            DataContract.from_yaml(yaml_content)


# ==============================================================================
# 5. DAG Topological Sorting Test Suite
# ==============================================================================

class TestDAGTopologicalSorting:
    def test_credit_mesh_topological_order(self, valid_credit_mesh_yaml: str):
        contract = DataContract.from_yaml(valid_credit_mesh_yaml)
        order = contract.get_dag_order()
        
        # Verify length and presence
        assert len(order) == 4
        assert set(order) == {"empresas", "propostas", "garantias", "operacoes"}

        # Dependency 1: empresas is parent of propostas and operacoes
        assert order.index("empresas") < order.index("propostas")
        assert order.index("empresas") < order.index("operacoes")

        # Dependency 2: propostas is parent of garantias and operacoes
        assert order.index("propostas") < order.index("garantias")
        assert order.index("propostas") < order.index("operacoes")

    def test_disconnected_tables_ordering(self):
        yaml_content = """
mesh_name: "disconnected_mesh"
tables:
  - name: "users"
    primary_key: "user_id"
    fields:
      - name: "user_id"
        type: "string"
  - name: "products"
    primary_key: "product_id"
    fields:
      - name: "product_id"
        type: "string"
  - name: "orders"
    primary_key: "order_id"
    fields:
      - name: "order_id"
        type: "string"
      - name: "user_id"
        type: "string"
        foreign_key: "users.user_id"
"""
        contract = DataContract.from_yaml(yaml_content)
        order = contract.get_dag_order()
        assert len(order) == 3
        # users must precede orders; products is independent
        assert order.index("users") < order.index("orders")
        assert "products" in order

    def test_diamond_dependency_ordering(self):
        yaml_content = """
mesh_name: "diamond_mesh"
tables:
  - name: "root"
    primary_key: "id_root"
    fields:
      - name: "id_root"
        type: "string"
  - name: "branch_a"
    primary_key: "id_a"
    fields:
      - name: "id_a"
        type: "string"
      - name: "id_root"
        type: "string"
        foreign_key: "root.id_root"
  - name: "branch_b"
    primary_key: "id_b"
    fields:
      - name: "id_b"
        type: "string"
      - name: "id_root"
        type: "string"
        foreign_key: "root.id_root"
  - name: "leaf"
    primary_key: "id_leaf"
    fields:
      - name: "id_leaf"
        type: "string"
      - name: "id_a"
        type: "string"
        foreign_key: "branch_a.id_a"
      - name: "id_b"
        type: "string"
        foreign_key: "branch_b.id_b"
"""
        contract = DataContract.from_yaml(yaml_content)
        order = contract.get_dag_order()
        assert order[0] == "root"
        assert order[-1] == "leaf"
        assert order.index("branch_a") < order.index("leaf")
        assert order.index("branch_b") < order.index("leaf")

    def test_dag_determinism_across_runs(self, valid_credit_mesh_yaml: str):
        contract1 = DataContract.from_yaml(valid_credit_mesh_yaml)
        contract2 = DataContract.from_yaml(valid_credit_mesh_yaml)
        assert contract1.get_dag_order() == contract2.get_dag_order()


# ==============================================================================
# 6. Parser I/O and Syntax Error Test Suite
# ==============================================================================

class TestParserIOAndSyntax:
    def test_invalid_yaml_syntax(self):
        bad_yaml = "mesh_name: [unterminated list"
        with pytest.raises(ContractParseError, match="Failed to parse YAML"):
            DataContract.from_yaml(bad_yaml)

    def test_non_dict_yaml(self):
        bad_yaml = "- a\n- b\n- c\n"
        with pytest.raises(ContractParseError, match="must be a valid mapping"):
            DataContract.from_yaml(bad_yaml)

    def test_non_existent_file_path(self):
        with pytest.raises(ContractParseError):
            DataContract.from_yaml(Path("non_existent_path_to_file.yaml"))

    def test_to_yaml_roundtrip(self, valid_credit_mesh_yaml: str):
        contract = DataContract.from_yaml(valid_credit_mesh_yaml)
        dumped_yaml = contract.to_yaml()
        reloaded = DataContract.from_yaml(dumped_yaml)
        assert reloaded.mesh_name == contract.mesh_name
        assert reloaded.get_table_names() == contract.get_table_names()
        assert reloaded.get_dag_order() == contract.get_dag_order()
```

---

## 5. Verification Commands & Execution Guide

### 5.1 Verification Commands

To verify the test suite once implemented by the Worker:

```bash
# 1. Run all unit tests for contract parser
pytest tests/unit/test_contract_parser.py -v

# 2. Run with short traceback and coverage report
pytest tests/unit/test_contract_parser.py -v --tb=short --cov=core.contract_parser

# 3. Target specific test classes
pytest tests/unit/test_contract_parser.py::TestDAGCycleDetection -v
pytest tests/unit/test_contract_parser.py::TestValidContracts -v
```

### 5.2 Environment Provisioning Guide

```bash
# Set up isolated virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install pinned dependencies
pip install -r requirements.txt

# Or install in editable mode with dev extras
pip install -e ".[dev]"
```
