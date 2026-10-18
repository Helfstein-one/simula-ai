# Project: Simula-AI

Autonomous relational data mocking framework for Data Mesh ecosystems. Ingests data contract YAML, executes iterative CoALA cognitive loop (LangGraph + OpenRouter DeepSeek) with isolated Pytest sandbox, generates Faker generators, validation test suites, exported datasets (JSON/CSV/Parquet), and interactive Mermaid ER diagrams.

## Architecture

Simula-AI follows a modular architecture separating cognitive orchestration, execution sandboxing, data modeling, deliverables generation, and dual interfaces:

```
                  ┌──────────────────────────────────────────────┐
                  │                 User Inputs                  │
                  │  (CLI Typer/Rich  OR  Streamlit Web UI)      │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │          Contract Parser & Schema            │
                  │      (contracts/exemplo_credito_mesh.yaml)   │
                  └──────────────┬───────────────────────────────┘
                                 │
         ┌───────────────────────┴───────────────────────┐
         │                                               │
         ▼                                               ▼
┌─────────────────────────────────┐   ┌──────────────────────────────────┐
│   Hybrid Mermaid ER Generator   │   │     CoALA Cognitive Loop         │
│   (core/diagram.py)             │   │     (core/graph.py StateGraph)   │
│   - Deterministic YAML extract  │   │                                  │
│   - Semantic cardinality rules  │   │  ┌────────────────────────────┐  │
│   - Output: mesh_er_diagram.mmd │   │  │ node_initialize            │  │
│   - Rich CLI / Streamlit HTML   │   │  └─────────────┬──────────────┘  │
└─────────────────────────────────┘   │                ▼                 │
                                      │  ┌────────────────────────────┐  │
                                      │  │ node_generate              │◄─┼──┐
                                      │  │ (OpenRouter DeepSeek/Mock) │  │  │ (traceback)
                                      │  │ (Regex <think> + AST parse)│  │  │
                                      │  └─────────────┬──────────────┘  │  │
                                      │                ▼                 │  │
                                      │  ┌────────────────────────────┐  │  │
                                      │  │ node_execute               │  │  │
                                      │  │ (Subprocess Pytest sandbox)│  │  │
                                      │  └─────────────┬──────────────┘  │  │
                                      │                ▼                 │  │
                                      │     [route_decision] ────────────┴──┘
                                      │       ├── status == 0 ──► SUCCESS
                                      │       └── iter >= MAX ──► FAILED
                                      └────────────────┬─────────────────┘
                                                       │
                                                       ▼
                                      ┌──────────────────────────────────┐
                                      │   Standalone Deliverables Engine │
                                      │   (core/exporter.py)             │
                                      │   ├── output/generator.py (Faker)│
                                      │   ├── output/test_mock.py (Pytest│
                                      │   └── output/datasets/           │
                                      │       (CSV, JSON, Parquet)       │
                                      └──────────────────────────────────┘
```

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1.1 | SimulaState Definition | TypedDict with procedural_memory, working_memory, episodic_memory, iterations, status | M2 | R1 |
| F1.2 | CoALA Memory Manager | Episodic traceback capture, history formatting, procedural rules injection | M2 | R1 |
| F1.3 | OpenRouter LLM Client | OpenRouter chat completions client with DeepSeek models, backoff & 429 fallback | M2 | R1 |
| F1.4 | Mock LLM Provider | Deterministic offline test double supporting test harness & CI (`SIMULA_MOCK_LLM`) | M2 | R1/E2E |
| F1.5 | Regex Think Stripping | Robust regex stripping `<think>...</think>` tags including unclosed tag lookaheads | M2 | R1/Acceptance |
| F1.6 | AST Code Extraction | Python markdown fence extraction and AST syntax validation (`ast.parse`) | M2 | R1 |
| F1.7 | Subprocess Pytest Sandbox | Ephemeral sandbox running `pytest simula_temp_test.py` with strict timeout, zero eval | M2 | R1/Acceptance |
| F1.8 | LangGraph StateGraph | Nodes (initialize, generate, execute), conditional edge `route_decision`, feedback loop | M2 | R1/Acceptance |
| F2.1 | Credit Mesh Contract YAML | 4-table credit schema (`empresas`, `propostas`, `garantias`, `operacoes`), PK/FKs, rules | M1 | R5 |
| F2.2 | Contract Parser & Validator | Pydantic models validating contract YAML schema, tables, fields, constraints | M1 | R1/R5 |
| F2.3 | Packaging & Dependencies | `pyproject.toml`, `requirements.txt`, `.env.example` | M1 | R5 |
| F3.1 | Deterministic ER Extraction | Schema extraction from YAML (tables, columns, types, PK, FK, UK) | M3 | R3 |
| F3.2 | Type Sanitization | Strip parentheses and invalid chars for Mermaid compliance | M3 | R3 |
| F3.3 | Semantic Cardinality Matrix | Infer and annotate relationship cardinalities (`||--o{`, `||--||`, etc.) | M3 | R3 |
| F3.4 | Mermaid Multi-Target Output | Rich terminal rendering, Streamlit HTML embedding, save to `output/mesh_er_diagram.mmd` | M3 | R3 |
| F4.1 | Standalone Generator Output | Export independent `output/generator.py` with topological DAG sorting and Faker logic | M4 | R4 |
| F4.2 | Standalone Test Suite Output | Export `output/test_mock.py` with 12 validation categories | M4 | R4 |
| F4.3 | Multi-Format Dataset Export | Generation of CSV, JSON, and Parquet files in `output/datasets/` | M4 | R4 |
| F5.1 | Interactive CLI (Typer/Rich) | Commands (`run`, `inspect`, `diagram`, `export`, `test`, `ui`), spinners, trees | M5 | R2 |
| F5.2 | Streamlit Web UI | Multi-tab app (Contract Studio, Agent Monitor, Mermaid Viewer, Data Preview) | M5 | R2/Acceptance |
| F5.3 | Rootless Containerfile | Podman-ready Containerfile with non-root user `simula:10001` and volume permissions | M5 | R5/Acceptance |
| F5.4 | Container Entrypoint | `entrypoint.sh` supporting CLI, Streamlit UI, and testing modes | M5 | R5 |
| F5.5 | Documentation (README.md) | Comprehensive documentation covering installation, CLI, UI, Podman, and architecture | M5 | R5 |
| F6.1 | E2E Opaque-Box Test Harness | Comprehensive 4-tier test runner and verification suite | M6 (E2E Track) | Acceptance |
| F6.2 | Adversarial Hardening (Tier 5) | White-box stress testing, corner cases, and coverage validation | M6 | Protocol |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Contract Specification & Foundation | `contracts/exemplo_credito_mesh.yaml`, `core/contract_parser.py`, `pyproject.toml`, `requirements.txt`, `.env.example` | none | DONE |
| M2 | CoALA Cognitive Loop & Sandbox | `core/state.py`, `core/memory.py`, `core/llm_client.py`, `core/code_parser.py`, `core/sandbox.py`, `core/graph.py` | M1 | PLANNED |
| M3 | Hybrid Mermaid ER Engine | `core/diagram.py`, multi-target renderers, `output/mesh_er_diagram.mmd` | M1 | PLANNED |
| M4 | Deliverables & Multi-Format Exporter | `core/exporter.py`, standalone `output/generator.py`, `output/test_mock.py`, CSV/JSON/Parquet export | M1, M2 | PLANNED |
| M5 | Dual Interface & Containerization | `cli/main.py` (Typer+Rich), `ui/app.py` (Streamlit), `Containerfile`, `entrypoint.sh`, `README.md` | M1, M2, M3, M4 | PLANNED |
| M6 | Final E2E Validation & Adversarial Hardening | Phase 1: 100% pass on E2E Test Suite (Tiers 1-4); Phase 2: Tier 5 Adversarial Hardening | M5, E2E Track | PLANNED |

### Parallel Track: E2E Testing Track
- **Scope**: Requirements-driven opaque-box test suite (`tests/e2e/test_tier1_features.py`, `test_tier2_boundaries.py`, `test_tier3_pairwise.py`, `test_tier4_workloads.py`).
- **Artifacts**: `TEST_INFRA.md`, `TEST_READY.md`.
- **Status**: PLANNED.

## Interface Contracts

### 1. `core.contract_parser` ↔ Consumers (`core.graph`, `core.diagram`, `cli`, `ui`)
- Class `DataContract`:
  ```python
  class FieldContract(BaseModel):
      name: str
      type: str
      nullable: bool = False
      primary_key: bool = False
      unique: bool = False
      foreign_key: Optional[str] = None  # format: "table.field"
      description: Optional[str] = None
      rules: List[str] = []

  class TableContract(BaseModel):
      name: str
      description: Optional[str] = None
      fields: List[FieldContract]
      business_rules: List[str] = []

  class DataContract(BaseModel):
      mesh_name: str
      version: str
      tables: List[TableContract]
      
      def get_table(self, name: str) -> Optional[TableContract]: ...
      def get_dag_order(self) -> List[str]: ...  # Topological sort based on FKs
  ```

### 2. `core.graph` (CoALA Loop) ↔ CLI & UI
- Function `run_simula_loop`:
  ```python
  def run_simula_loop(
      contract_yaml_path: str,
      max_iterations: int = 5,
      model: str = "deepseek/deepseek-r1",
      mock_mode: bool = False,
  ) -> Iterator[SimulaEvent]: ...
  # Yields SimulaEvent(step, iteration, state, message) for live spinners/progress
  ```

### 3. `core.diagram` (Mermaid ER) ↔ CLI, UI & Exporter
- Function `generate_mermaid_er`:
  ```python
  def generate_mermaid_er(contract: DataContract) -> str: ...
  # Returns valid Mermaid erDiagram syntax with tables, attributes, and relationships
  ```

### 4. `core.exporter` (Deliverables) ↔ CLI & UI
- Function `export_deliverables`:
  ```python
  def export_deliverables(
      generated_code: str,
      output_dir: Path,
      contract: DataContract,
      generate_datasets: bool = True,
      rows: int = 50,
      formats: List[str] = ["csv", "json", "parquet"],
  ) -> Dict[str, Path]: ...
  # Returns paths to generator.py, test_mock.py, and generated dataset files
  ```

## Code Layout

```
/Users/mauriciohelfstein/dev/simula-ai/
├── contracts/
│   └── exemplo_credito_mesh.yaml        # Sample 4-table credit mesh contract
├── core/
│   ├── __init__.py
│   ├── contract_parser.py               # YAML contract ingestion & validation
│   ├── state.py                         # SimulaState TypedDict definition
│   ├── memory.py                        # Procedural & episodic memory management
│   ├── llm_client.py                    # OpenRouter DeepSeek client with 429 fallback & mock
│   ├── code_parser.py                   # Regex <think> stripping & AST validation
│   ├── sandbox.py                       # Subprocess Pytest sandbox execution
│   ├── diagram.py                       # Hybrid Mermaid ER diagram generator
│   ├── exporter.py                      # Standalone generator & test exporter
│   └── graph.py                         # LangGraph StateGraph & event streamer
├── cli/
│   ├── __init__.py
│   └── main.py                          # Typer + Rich interactive CLI
├── ui/
│   ├── __init__.py
│   └── app.py                           # Streamlit Web UI
├── output/                              # Target directory for generated artifacts
│   ├── generator.py
│   ├── test_mock.py
│   ├── mesh_er_diagram.mmd
│   └── datasets/
│       ├── csv/
│       ├── json/
│       └── parquet/
├── tests/
│   ├── __init__.py
│   ├── unit/                            # Unit tests for core modules
│   └── e2e/                             # Opaque-box requirement-driven E2E tests
│       ├── test_tier1_features.py
│       ├── test_tier2_boundaries.py
│       ├── test_tier3_pairwise.py
│       └── test_tier4_workloads.py
├── Containerfile                        # Podman rootless container definition
├── entrypoint.sh                        # Dual CLI/UI container entrypoint
├── pyproject.toml                       # Python package specification
├── requirements.txt                     # Pinned dependencies
├── .env.example                         # Environment configuration template
└── README.md                            # Complete framework documentation
```
