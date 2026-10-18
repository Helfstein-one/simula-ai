# Simula-AI — End-to-End Test Infrastructure Specification

## 1. Overview & Architectural Philosophy

Simula-AI is an autonomous relational data mocking framework for Data Mesh ecosystems. It ingests data contracts in YAML format and executes an iterative CoALA cognitive loop (LangGraph + OpenRouter DeepSeek) alongside an isolated Pytest execution sandbox to produce standalone Faker data generators, Pytest verification suites, multi-format datasets (CSV, JSON, Parquet), and interactive Mermaid entity-relationship diagrams.

The E2E Test Suite provides **opaque-box, requirement-driven verification** of the entire Simula-AI framework, adhering strictly to requirements R1 through R5 defined in `ORIGINAL_REQUEST.md` and the interface contracts in `PROJECT.md`.

### Core Tenets of the E2E Test Suite
1. **Opaque-Box Verification**: Tests validate observable contracts, outputs, CLI interfaces, and state transitions without reliance on internal implementation hacks.
2. **Deterministic Execution**: Tests operate offline via the deterministic Mock LLM provider (`SIMULA_MOCK_LLM=true`) and standard temporary sandboxes to ensure 100% reproducible execution in CI and local developer workstations.
3. **Progressive Testability**: The test suite gracefully checks for module readiness, compiling cleanly at all times while validating modules as they become available.
4. **Adversarial & Boundary Rigor**: Edge cases, malformed schemas, syntax deviations, unclosed tags, and resource boundary conditions are tested systematically.

---

## 2. 4-Tier Test Suite Methodology

The test suite is structured into four distinct verification tiers under `tests/e2e/`:

```
tests/e2e/
├── test_tier1_features.py     # Tier 1: Core Feature Verification (R1 - R5)
├── test_tier2_boundaries.py   # Tier 2: Boundary, Edge Cases & Error Handling
├── test_tier3_pairwise.py     # Tier 3: Cross-Feature Interactions & Pairwise Combinations
└── test_tier4_workloads.py    # Tier 4: Real-World Credit Mesh Workload Simulation
```

### Tier 1: Feature Coverage (`test_tier1_features.py`)
- **Objective**: Validate the happy path and primary behavior for each core requirement in isolation.
- **Scope**:
  - **R1 State & Memory**: `SimulaState` TypedDict structure, episodic memory traceback logging, procedural memory rules.
  - **R1 Code Parsing**: Regex `<think>` tag stripping, markdown code fence extraction, AST syntax validation (`ast.parse`).
  - **R1 Sandbox**: Subprocess Pytest execution in isolated temporary directory with zero `eval()` and strict timeout.
  - **R2 CLI**: Typer CLI command availability (`run`, `inspect`, `diagram`, `export`, `test`, `ui`), `--help`, and flag validation.
  - **R3 Mermaid ER**: Deterministic schema extraction from contract YAML, type sanitization, and valid Mermaid `erDiagram` generation.
  - **R4 Deliverables**: Standalone generator export (`output/generator.py`), test suite export (`output/test_mock.py`), and dataset file creation (`.csv`, `.json`, `.parquet`).
  - **R5 Contract Loading**: Ingestion and validation of `contracts/exemplo_credito_mesh.yaml` with 4 credit tables (`empresas`, `propostas`, `garantias`, `operacoes`).

### Tier 2: Boundary & Edge Conditions (`test_tier2_boundaries.py`)
- **Objective**: Stress boundary conditions, extreme inputs, syntax anomalies, and error paths.
- **Scope**:
  - **Unclosed `<think>` Tags**: Truncated LLM responses missing `</think>` tags with lookahead code preservation.
  - **Non-zero Return Codes**: Pytest sandbox handling of syntax errors (exit code 2), test assertion failures (exit code 1), and general exceptions.
  - **Subprocess Timeout Expiration**: Infinite loops in generated code triggering `subprocess.TimeoutExpired`, returning exit code -1 and capturing timeout errors.
  - **Malformed YAML Contracts**: Syntax errors, missing mandatory top-level keys (`tables`, `version`), and invalid field definitions.
  - **Missing Optional Fields**: Contracts omitting optional metadata (descriptions, nullability defaults, format).
  - **Zero-Row & Extreme Dataset Sizes**: Exporter and generator handling `rows=0` and large row counts gracefully.
  - **Max Iterations Exhaustion**: Cognitive loop terminating when `iterations >= MAX_ITERATIONS` without infinite looping.

### Tier 3: Pairwise Combinations (`test_tier3_pairwise.py`)
- **Objective**: Verify that interconnected components collaborate seamlessly across subsystem boundaries.
- **Scope**:
  - **CLI + CoALA Loop + Exporter**: Running CLI `--mock` triggers the cognitive loop, validates code in sandbox, and exports all deliverables to disk.
  - **Contract Parser + Mermaid Generator**: Complex multi-table schemas with foreign keys, compound relationships, and nullable fields correctly converted to Mermaid diagrams.
  - **CoALA Feedback Loop + Episodic Memory**: Failure in iteration 0 injects traceback into episodic memory; subsequent iteration resolves failure and successfully terminates with exit code 0.
  - **Streamlit App State Reflection**: Simulated web UI state transitions across `INIT`, `GENERATING`, `EXECUTING`, and `SUCCESS`.

### Tier 4: Real-World Workload Simulation (`test_tier4_workloads.py`)
- **Objective**: End-to-end operational execution of the complete 4-table Brazilian corporate credit mesh scenario.
- **Scope**:
  - Full simulation pipeline on `contracts/exemplo_credito_mesh.yaml`.
  - Verifying all 4 tables: `empresas`, `propostas`, `garantias`, `operacoes`.
  - **Primary & Foreign Key Referential Integrity**: 100% of foreign keys in child tables resolve to valid parent primary keys; zero orphan records.
  - **Domain Business Rules**:
    - Valid CNPJ format regex (`^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$`).
    - Chronological consistency: `data_contratacao >= data_solicitacao`.
    - Value consistency: `valor_contratado <= valor_solicitado`.
    - Proposal approval filtering: Only `APROVADA` proposals generate `operacoes`.
  - **Deliverables Generation & Integrity**:
    - Valid standalone `output/generator.py` executable without Simula framework dependencies.
    - Accompanying `output/test_mock.py` test suite passing 100% when executed with `pytest`.
    - Multi-format datasets produced in CSV, JSON, and Parquet.

---

## 3. Feature Inventory to Test Mapping Matrix

| Feature ID | Feature Name | Requirement | Primary Test Tier | Test Function / Class |
|---|---|---|---|---|
| **F1.1** | SimulaState Definition | R1 | Tier 1 | `test_simula_state_structure` |
| **F1.2** | CoALA Memory Manager | R1 | Tier 1, 3 | `test_memory_episodic_traceback_injection` |
| **F1.3** | OpenRouter LLM Client | R1 | Tier 1 | `test_llm_client_headers_and_payload` |
| **F1.4** | Mock LLM Provider | R1, E2E | Tier 1, 3 | `test_mock_llm_deterministic_output` |
| **F1.5** | Regex Think Stripping | R1, Acceptance | Tier 1, 2 | `test_regex_think_stripping_standard`, `test_unclosed_think_tag` |
| **F1.6** | AST Code Extraction | R1 | Tier 1, 2 | `test_ast_code_extraction_and_validation` |
| **F1.7** | Subprocess Sandbox | R1, Acceptance | Tier 1, 2 | `test_sandbox_subprocess_execution`, `test_sandbox_timeout_expiration` |
| **F1.8** | LangGraph StateGraph | R1, Acceptance | Tier 1, 3 | `test_cognitive_loop_routing_success`, `test_cognitive_loop_retry_flow` |
| **F2.1** | Credit Mesh Contract YAML | R5 | Tier 1, 4 | `test_credit_mesh_contract_exists_and_valid` |
| **F2.2** | Contract Parser & Validator | R1, R5 | Tier 1, 2 | `test_contract_parser_model_validation`, `test_contract_parser_malformed_yaml` |
| **F2.3** | Packaging & Dependencies | R5 | Tier 1 | `test_packaging_and_dependencies` |
| **F3.1** | Deterministic ER Extraction | R3 | Tier 1, 3 | `test_mermaid_er_deterministic_extraction` |
| **F3.2** | Type Sanitization | R3 | Tier 1, 2 | `test_mermaid_type_sanitization` |
| **F3.3** | Semantic Cardinality Matrix | R3 | Tier 1, 3 | `test_mermaid_cardinality_annotations` |
| **F3.4** | Mermaid Multi-Target Output | R3 | Tier 1 | `test_mermaid_file_persistence` |
| **F4.1** | Standalone Generator Output | R4 | Tier 1, 4 | `test_standalone_generator_execution` |
| **F4.2** | Standalone Test Suite Output | R4 | Tier 1, 4 | `test_standalone_test_mock_execution` |
| **F4.3** | Multi-Format Dataset Export | R4 | Tier 1, 4 | `test_multi_format_dataset_export` |
| **F5.1** | Interactive CLI (Typer/Rich) | R2 | Tier 1, 3 | `test_cli_commands_and_help`, `test_cli_mock_run_e2e` |
| **F5.2** | Streamlit Web UI | R2 | Tier 1, 3 | `test_streamlit_app_import_and_state` |
| **F5.3** | Rootless Containerfile | R5 | Tier 1 | `test_containerfile_rootless_specification` |
| **F5.4** | Container Entrypoint | R5 | Tier 1 | `test_container_entrypoint_script` |
| **F5.5** | Documentation (README.md) | R5 | Tier 1 | `test_documentation_completeness` |

---

## 4. Test Runner & Execution Guide

### Prerequisites
- Python 3.12+ (Python 3.12 or 3.14 recommended).
- Pytest 8.0+ installed.
- Required runtime packages: `pydantic`, `pyyaml`, `faker`, `pandas`, `pyarrow`, `typer`, `rich`.

### Environment Configuration
The test runner operates in deterministic offline mode by setting:
```bash
export SIMULA_MOCK_LLM=true
export SIMULA_SANDBOX_TIMEOUT=10
```

### Execution Commands

1. **Run Full E2E Test Suite**:
   ```bash
   python3 -m pytest tests/e2e/ -v
   ```

2. **Run Individual Tiers**:
   ```bash
   # Tier 1: Core Feature Verification
   python3 -m pytest tests/e2e/test_tier1_features.py -v

   # Tier 2: Boundary & Corner Cases
   python3 -m pytest tests/e2e/test_tier2_boundaries.py -v

   # Tier 3: Pairwise Combinations
   python3 -m pytest tests/e2e/test_tier3_pairwise.py -v

   # Tier 4: Real-World Credit Mesh Workload
   python3 -m pytest tests/e2e/test_tier4_workloads.py -v
   ```

3. **Run with Verbose Output & Traceback**:
   ```bash
   python3 -m pytest tests/e2e/ -v --tb=short
   ```

4. **Verify Test Suite Collection Only (Dry-Run)**:
   ```bash
   python3 -m pytest tests/e2e/ --collect-only
   ```
