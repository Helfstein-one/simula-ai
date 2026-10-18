# Technical Survey & Specification: Dual Interface (CLI/UI), Deliverables & Data Contract (R2, R4, R5)

**Author:** Explorer 2 (Survey Phase)  
**Date:** 2026-10-12  
**Target Systems:** Typer/Rich CLI, Streamlit UI, Standalone Generator & Pytest Suite, Multi-format Data Export, Credit Mesh Contract

---

## 1. System Architecture & Component Boundaries

Simula-AI is an autonomous relational data mocking framework designed for Data Mesh ecosystems. It operates across modular boundaries:

```
simula-ai/
├── contracts/                        # Data Contract schemas (YAML)
│   └── exemplo_credito_mesh.yaml     # Multi-table credit mesh specification
├── core/                             # CoALA Cognitive Loop & LangGraph engine
│   ├── state.py                      # SimulaState TypedDict (Working, Episodic, Procedural)
│   ├── nodes.py                      # Internal action (LLM), external action (sandbox), router
│   ├── loop.py                       # LangGraph StateGraph builder & execution stream
│   └── sandbox.py                    # Subprocess Pytest execution sandbox
├── cli/                              # Dual Interface: Terminal CLI
│   ├── main.py                       # Typer entrypoint and commands
│   └── renderers.py                  # Rich spinners, tables, trees, syntax viewers
├── ui/                               # Dual Interface: Web Dashboard
│   ├── app.py                        # Streamlit main application & multi-tab layout
│   ├── components/                   # UI components (ERD viewer, YAML editor, State inspect)
│   └── bridge.py                     # Generator event stream bridge for Streamlit
├── export/                           # Data Export & Transformation utilities
│   ├── serializers.py                # CSV, JSON, Parquet export engines (pyarrow/pandas)
│   └── validator.py                  # Contract schema validator (Pydantic model)
└── output/                           # Deliverables destination
    ├── generator.py                  # Standalone standalone mock generator
    ├── test_mock.py                  # Accompanying verification Pytest suite
    ├── mesh_er_diagram.mmd           # Exported Mermaid ER diagram
    └── datasets/                     # Simulated datasets
        ├── csv/
        ├── json/
        └── parquet/
```

---

## 2. Typer + Rich CLI Architecture & Specification (R2)

### 2.1 CLI Architecture & Command Structure

The CLI is built with **Typer** and styled with **Rich**. It exposes a clear, UNIX-compliant toolset via console command `simula` (configured in `pyproject.toml` as `[project.scripts] simula = "cli.main:app"`).

```
simula [OPTIONS] COMMAND [ARGS]...
```

#### Command Matrix

| Command | Arguments | Options / Flags | Description |
|---|---|---|---|
| `run` *(default)* | `CONTRACT_PATH: Path` | `--iterations, -m INT` (default: 5)<br>`--output-dir, -o PATH` (default: `output/`)<br>`--rows, -n INT` (default: 100)<br>`--format, -f TEXT` (default: `csv,json,parquet`)<br>`--model TEXT` (default: `deepseek/deepseek-chat`)<br>`--seed INT` (default: 42)<br>`--no-diagram`<br>`--verbose, -v` | Executes the full CoALA loop: loads contract, runs LLM generator & sandbox validation, exports `generator.py`, `test_mock.py`, ER diagram, and datasets. |
| `inspect` | `CONTRACT_PATH: Path` | `--detailed / --summary` | Parses contract YAML and renders tables, fields, constraints, types, and foreign key relationships in Rich tables. |
| `diagram` | `CONTRACT_PATH: Path` | `--output, -o PATH` (default: `output/mesh_er_diagram.mmd`)<br>`--print-only` | Extracts relational topology and outputs a Mermaid ER diagram to stdout or `.mmd` file. |
| `export` | `CONTRACT_PATH: Path` | `--generator, -g PATH` (default: `output/generator.py`)<br>`--rows, -n INT` (default: 100)<br>`--output-dir, -o PATH` (default: `output/datasets`)<br>`--format, -f TEXT` (default: `csv,json,parquet`)<br>`--seed INT` (default: 42) | Runs the standalone generator directly (no LLM required) to produce dataset files. |
| `test` | `[TEST_FILE]` (default: `output/test_mock.py`) | `--timeout INT` (default: 30)<br>`--verbose, -v` | Runs the Pytest validation suite against generated data inside the isolated sandbox. |
| `ui` | *none* | `--port INT` (default: 8501)<br>`--host TEXT` (default: `0.0.0.0`)<br>`--browser / --no-browser` | Launches the Streamlit Web UI via subprocess. |

### 2.2 Rich Terminal Experience & Renderers

Rich components are utilized to provide continuous situational awareness:

1. **Header Banner**: Styled panel with ASCII / Unicode art and system info (contract name, active OpenRouter model, target output path).
2. **Schema Tree & Table (`rich.tree.Tree`, `rich.table.Table`)**:
   - `simula inspect` renders a tree displaying tables with branch leaves for fields: `[green]empresa_id[/green] (uuid, PK)` -> `[yellow]cnpj[/yellow] (string, regex)`.
   - Rich Table displaying foreign key mapping: `Child Table` -> `FK Field` -> `Parent Table` -> `Parent PK` -> `Cardinality`.
3. **Live Spinners & Progress (`rich.live.Live`, `rich.spinner.Spinner`, `rich.progress.Progress`)**:
   - Progress bar tracking CoALA iterations: `[Iteration 2/5]`.
   - Dynamic Spinner messages:
     - `⠋ Calling OpenRouter DeepSeek (internal_action_generate)...`
     - `⠙ Running Pytest sandbox in isolation (external_action_execute)...`
     - `⠹ Routing decision (route_decision): Evaluating traceback...`
4. **Episodic Memory Error Panel (`rich.panel.Panel`, `rich.syntax.Syntax`)**:
   - On test failure, displays a high-visibility Red Panel containing:
     - Iteration count and error category (e.g., `AssertionError: Foreign Key Violation`).
     - Truncated Pytest traceback snippet highlighted with `rich.syntax.Syntax(..., "pytb")`.
     - Reflection prompt fed back into LLM memory for next cycle.
5. **Execution Summary & Artifact Tree**:
   - On success (return code 0), displays Green Panel: `🎉 Generation Validated & Completed in X iterations!`.
   - Artifact summary tree listing:
     - `output/generator.py` [green]OK[/green] (Size: 4.2 KB)
     - `output/test_mock.py` [green]OK[/green] (Passed: 8/8 tests)
     - `output/mesh_er_diagram.mmd` [green]OK[/green]
     - `output/datasets/`
       - `csv/` (4 files, 450 rows)
       - `json/` (4 files, 450 rows)
       - `parquet/` (4 files, 450 rows)

---

## 3. Streamlit Web UI Architecture & Specification (R2)

### 3.1 UI Architecture & Execution Lifecycle

The Streamlit UI (`ui/app.py`) provides an interactive workbench for data engineers. Because Streamlit operates on a full-script rerun model, the connection with LangGraph requires clean state management:

```
┌────────────────────────────────────────────────────────┐
│                   Streamlit Frontend                   │
│  Sidebar (Params) │ Tabs (Editor, Monitor, ERD, Preview)│
└───────────────────────────┬────────────────────────────┘
                            │ User clicks "Run Simulation"
                            ▼
┌────────────────────────────────────────────────────────┐
│                   State Bridge (ui/bridge.py)          │
│  - Wraps core.loop.stream_loop() as Python Generator   │
│  - Emits: StateUpdate(node, iteration, state, status)   │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│                   LangGraph CoALA Loop                 │
│  generate -> execute_sandbox -> route_decision         │
└────────────────────────────────────────────────────────┘
```

#### Streamlit State Management (`st.session_state`)

The following variables persist across reruns:
- `st.session_state.contract_content`: Current YAML string in editor.
- `st.session_state.contract_parsed`: Dict/Pydantic representation of the contract.
- `st.session_state.loop_status`: Current lifecycle state (`"IDLE"`, `"RUNNING"`, `"SUCCESS"`, `"FAILED"`).
- `st.session_state.iterations_history`: List of iteration records (iteration number, code snapshot, stdout/stderr, passed boolean, timestamp).
- `st.session_state.latest_state`: Complete `SimulaState` snapshot.
- `st.session_state.generated_generator_code`: Python source string for `generator.py`.
- `st.session_state.generated_test_code`: Python source string for `test_mock.py`.
- `st.session_state.datasets`: Dict of `{table_name: pd.DataFrame}` holding generated mock data.
- `st.session_state.mermaid_erd`: Extracted Mermaid ER diagram string.

### 3.2 Layout & Component Specifications

#### Sidebar
- **Logo & Title**: "Simula-AI: Autonomous Data Mesh Mocking".
- **Environment & LLM Config**:
  - OpenRouter API Key input (defaults to `OPENROUTER_API_KEY` from environment, password masked).
  - Model selection dropdown: `deepseek/deepseek-chat` (default), `deepseek/deepseek-r1`.
  - Fallback model toggle (auto-fallback on HTTP 429).
- **Simulation Parameters**:
  - Max Iterations slider: `1` to `10` (default: `5`).
  - Rows per Table slider: `10` to `5000` (default: `100`).
  - Export Formats multi-select: `CSV`, `JSON`, `Parquet` (default: all three).
  - Random Seed number input (default: `42`).
- **Control Buttons**:
  - `▶ Run Simulation` (primary button, disabled while running).
  - `↺ Reset State` (secondary button).
  - `📥 Export All Artifacts (ZIP)` (enabled when `loop_status == "SUCCESS"`).

#### Tab 1: Contract Studio (YAML Editor & Schema Tree)
- **File Ingestion**:
  - `st.file_uploader`: Upload `.yaml` or `.yml` contracts.
  - Preset Contract dropdown: includes `contracts/exemplo_credito_mesh.yaml`.
- **Interactive Editor**:
  - `st.text_area` or `streamlit_ace` editor with syntax highlighting (`language="yaml"`).
  - On-the-fly syntax & schema validation pill: `Valid YAML` / `Invalid YAML (Line X, Col Y)`.
- **Parsed Schema Inspector**:
  - Expandable cards for each table (`empresas`, `propostas`, `garantias`, `operacoes`).
  - Table of fields showing: Field Name, Data Type, Constraints, Faker Provider, Foreign Key target.

#### Tab 2: Agent Monitor & Episodic Memory Inspection
- **Live Status Container (`st.status`)**:
  - Automatically expands during execution showing real-time step messages:
    - `🤖 Iteration {n}: Generating generator.py and test_mock.py...`
    - `🧪 Iteration {n}: Running isolated Pytest sandbox...`
    - `⚖️ Iteration {n}: Pytest passed / failed. Routing...`
- **Memory Triad View**:
  1. **Procedural Memory**: Expandable view of system prompt, data engineering rules, and testing standards injected into LLM.
  2. **Working Memory**: Active prompt payload, current candidate code blocks.
  3. **Episodic Memory (The Traceback Timeline)**:
     - Accordion cards for each iteration:
       - Iteration 1: `❌ FAILED (AssertionError: propostas FK not found in empresas)` -> Expand to view exact traceback, diff generated, and reflection fed to next turn.
       - Iteration 2: `✅ PASSED (Sandbox Return Code: 0, 8 passed in 0.42s)`.
- **Metrics Bar**:
  - Columns: Iterations Used, Total Sandbox Execution Time, Status Badge (`SUCCESS`/`FAILED`).

#### Tab 3: Interactive Mermaid ER Diagram
- **Rendering Engine**:
  - Rendered using `st.components.v1.html` embedding `mermaid.js` v10 via CDN, with responsive container sizing and clean theme matching dark/light mode.
  - Fallback code view in `st.code(mermaid_code, language="mermaid")`.
- **Interactivity & Controls**:
  - "Download Diagram (.mmd)" button (`st.download_button`).
  - View toggle: "Contract Structural Schema" vs "LLM Semantic Annotated Schema".

#### Tab 4: Generated Code & Sandbox Validation
- **Code Viewer Tabs**:
  - Subtab 1: `generator.py` (rendered with `st.code(..., language="python")` with copy button).
  - Subtab 2: `test_mock.py` (rendered with `st.code(..., language="python")` with copy button).
- **Sandbox Test Output**:
  - Pytest execution terminal display: terminal output box (`st.code(pytest_output, language="bash")`).
  - Verification checkmarks for individual test cases.

#### Tab 5: Data Preview & Export
- **Table Selector**: Tabs or segmented radio buttons for tables: `empresas`, `propostas`, `garantias`, `operacoes`.
- **Data Viewer**:
  - `st.dataframe` showing generated records with column search, sorting, and row count metrics.
  - Quick column statistics (distinct counts, null percentage, min/max for numeric fields).
- **Download Action Bar**:
  - `Download CSV` (`st.download_button`).
  - `Download JSON` (`st.download_button`).
  - `Download Parquet` (`st.download_button`).
  - `Download All Datasets (.zip)` containing directory structure.

---

## 4. Deliverables & Data Export Architecture (R4)

### 4.1 Standalone Generator Script (`output/generator.py`)

A critical requirement is that `output/generator.py` must be **100% standalone and executable outside of Simula-AI's agent runtime**. It must have NO dependencies on LangGraph, OpenRouter, or internal framework packages.

#### Runtime Dependencies for `generator.py`
- Python standard library (`argparse`, `sys`, `pathlib`, `uuid`, `datetime`, `random`)
- `faker >= 24.0.0`
- `pandas >= 2.0.0`
- `pyarrow >= 14.0.0` (or `fastparquet`)

#### Architecture of `output/generator.py`
```python
"""Standalone Relational Mock Data Generator.

Auto-generated by Simula-AI.
Execution: python output/generator.py --rows 100 --output-dir output/datasets --format all
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import random
import uuid
from faker import Faker
import pandas as pd


def seed_everything(seed: int = 42) -> Faker:
  random.seed(seed)
  fake = Faker("pt_BR")
  Faker.seed(seed)
  return fake


def generate_empresas(n: int, fake: Faker) -> pd.DataFrame:
  """Topological level 0: No foreign keys."""
  records = []
  for _ in range(n):
    empresa_id = str(uuid.uuid4())
    records.append({
        "empresa_id": empresa_id,
        "cnpj": fake.cnpj(),
        "razao_social": fake.company(),
        "nome_fantasia": fake.company_suffix(),
        "data_fundacao": fake.date_between(
            start_date="-15y", end_date="-1y"
        ).isoformat(),
        "faturamento_anual": round(random.uniform(150000.0, 50000000.0), 2),
        "setor": random.choice(
            ["INDUSTRIA", "COMERCIO", "SERVICOS", "AGRONEGOCIO", "TECNOLOGIA"]
        ),
        "score_credito": random.randint(300, 950),
        "status_cadastral": random.choice(
            ["ATIVO", "ATIVO", "ATIVO", "INATIVO", "RECUPERACAO_JUDICIAL"]
        ),
    })
  return pd.DataFrame(records)


def generate_propostas(
    n: int, empresas_df: pd.DataFrame, fake: Faker
) -> pd.DataFrame:
  """Topological level 1: References empresas."""
  empresa_ids = empresas_df["empresa_id"].tolist()
  records = []
  for _ in range(n):
    proposta_id = str(uuid.uuid4())
    empresa_id = random.choice(empresa_ids)
    dt_solicitacao = fake.date_time_between(
        start_date="-180d", end_date="now"
    ).isoformat()
    valor_solicitado = round(random.uniform(20000.0, 2000000.0), 2)
    records.append({
        "proposta_id": proposta_id,
        "empresa_id": empresa_id,
        "data_solicitacao": dt_solicitacao,
        "valor_solicitado": valor_solicitado,
        "prazo_meses": random.choice([12, 24, 36, 48, 60, 72]),
        "taxa_juros_mensal": round(random.uniform(0.015, 0.038), 4),
        "finalidade": random.choice(
            ["CAPITAL_GIRO", "EXPANSAO", "EQUIPAMENTOS", "REFINANCIAMENTO"]
        ),
        "status": random.choice(
            ["EM_ANALISE", "APROVADA", "APROVADA", "REJEITADA", "CANCELADA"]
        ),
    })
  return pd.DataFrame(records)


def generate_garantias(
    n: int, propostas_df: pd.DataFrame, fake: Faker
) -> pd.DataFrame:
  """Topological level 2: References propostas."""
  proposta_ids = propostas_df["proposta_id"].tolist()
  records = []
  for _ in range(n):
    garantia_id = str(uuid.uuid4())
    proposta_id = random.choice(proposta_ids)
    records.append({
        "garantia_id": garantia_id,
        "proposta_id": proposta_id,
        "tipo_garantia": random.choice(
            ["IMOVEL", "VEICULO", "RECEBIVEIS", "AVAL", "FIANCA_BANCARIA"]
        ),
        "valor_avaliado": round(random.uniform(30000.0, 5000000.0), 2),
        "percentual_cobertura": round(random.uniform(0.5, 1.8), 2),
        "descricao": fake.sentence(nb_words=6),
        "status_avaliacao": random.choice(["AVALIADA", "PENDENTE", "REJEITADA"]),
    })
  return pd.DataFrame(records)


def generate_operacoes(
    propostas_df: pd.DataFrame, empresas_df: pd.DataFrame, fake: Faker
) -> pd.DataFrame:
  """Topological level 2: References approved propostas and matching empresas."""
  aprovadas = propostas_df[propostas_df["status"] == "APROVADA"].to_dict(
      "records"
  )
  records = []
  op_counter = 1
  for p in aprovadas:
    # 1:1 conversion for approved proposals (or subset)
    operacao_id = str(uuid.uuid4())
    dt_sol = datetime.fromisoformat(p["data_solicitacao"])
    dt_contratacao = (dt_sol + timedelta(days=random.randint(2, 20))).isoformat()
    val_solicitado = float(p["valor_solicitado"])
    val_contratado = round(val_solicitado * random.uniform(0.8, 1.0), 2)
    saldo_devedor = round(val_contratado * random.uniform(0.2, 0.95), 2)
    n_parcelas = int(p["prazo_meses"])
    parcelas_pagas = random.randint(1, max(1, n_parcelas - 2))

    records.append({
        "operacao_id": operacao_id,
        "proposta_id": p["proposta_id"],
        "empresa_id": p["empresa_id"],
        "codigo_contrato": f"OP-2026-{op_counter:06d}",
        "data_contratacao": dt_contratacao,
        "valor_contratado": val_contratado,
        "saldo_devedor": saldo_devedor,
        "numero_parcelas": n_parcelas,
        "parcelas_pagas": parcelas_pagas,
        "status_operacao": random.choice(
            ["EM_DIA", "EM_DIA", "EM_DIA", "ATRASO"]
        ),
    })
    op_counter += 1
  return pd.DataFrame(records)


def export_datasets(
    datasets: dict[str, pd.DataFrame], output_dir: Path, formats: list[str]
):
  for fmt in formats:
    target_dir = output_dir / fmt
    target_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in datasets.items():
      if fmt == "csv":
        df.to_csv(target_dir / f"{table_name}.csv", index=False, encoding="utf-8")
      elif fmt == "json":
        df.to_json(
            target_dir / f"{table_name}.json",
            orient="records",
            indent=2,
            force_ascii=False,
            date_format="iso",
        )
      elif fmt == "parquet":
        df.to_parquet(
            target_dir / f"{table_name}.parquet",
            index=False,
            engine="pyarrow",
            compression="snappy",
        )


def main():
  parser = argparse.ArgumentParser(
      description="Simula-AI Standalone Relational Mock Generator"
  )
  parser.add_argument(
      "--rows",
      "-n",
      type=int,
      default=100,
      help="Base sample size for primary entities",
  )
  parser.add_argument(
      "--output-dir",
      "-o",
      type=Path,
      default=Path("output/datasets"),
      help="Output directory",
  )
  parser.add_argument(
      "--format",
      "-f",
      type=str,
      default="csv,json,parquet",
      help="Comma-separated formats: csv,json,parquet,all",
  )
  parser.add_argument(
      "--seed", "-s", type=int, default=42, help="Deterministic random seed"
  )
  args = parser.parse_args()

  formats = (
      ["csv", "json", "parquet"]
      if args.format.lower() == "all"
      else [fmt.strip().lower() for fmt in args.format.split(",")]
  )
  fake = seed_everything(args.seed)

  print(f"[+] Generating mock data (base rows: {args.rows}, seed: {args.seed})...")
  empresas = generate_empresas(args.rows, fake)
  propostas = generate_propostas(int(args.rows * 1.5), empresas, fake)
  garantias = generate_garantias(int(args.rows * 1.8), propostas, fake)
  operacoes = generate_operacoes(propostas, empresas, fake)

  datasets = {
      "empresas": empresas,
      "propostas": propostas,
      "garantias": garantias,
      "operacoes": operacoes,
  }

  export_datasets(datasets, args.output_dir, formats)
  print(f"[✓] Successfully exported datasets to {args.output_dir} ({formats})")


if __name__ == "__main__":
  main()
```

### 4.2 Accompanying Pytest Suite (`output/test_mock.py`)

The pytest suite accompanies the generator. It runs in the sandboxed subprocess during the CoALA loop AND can be independently executed by users (`pytest output/test_mock.py -v`).

#### Verification Assertion Matrix

| Test Function | Target Table(s) | Verified Property | Failure Implication |
|---|---|---|---|
| `test_tables_non_empty` | All tables | Row count > 0 | Generator produced empty dataframe |
| `test_column_presence` | All tables | Every field defined in YAML contract exists in dataframe | Missing column name or schema mismatch |
| `test_primary_key_uniqueness` | All tables | `df[pk].nunique() == len(df)` and `df[pk].isna().sum() == 0` | Duplicate IDs or null PKs generated |
| `test_foreign_key_referential_integrity` | `propostas`, `garantias`, `operacoes` | Child FK values are a strict subset of Parent PK values | Orphan child records; referential integrity broken |
| `test_nullability_constraints` | All non-null fields | Zero NaN / None values in constrained columns | Null values generated in required fields |
| `test_cnpj_format_and_validity` | `empresas` | CNPJ matches `^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$` | Invalid tax ID formatting |
| `test_enum_constraints` | `setor`, `finalidade`, `status`, `tipo_garantia`, `status_operacao` | All column values are members of declared enum set | Hallucinated enum values |
| `test_value_ranges_and_signs` | All numeric fields | `valor_solicitado > 0`, `prazo_meses between 6 and 120`, `taxa_juros > 0`, `faturamento_anual > 0` | Negative or out-of-range financial values |
| `test_relational_chronology` | `propostas`, `operacoes` | `operacoes.data_contratacao >= propostas.data_solicitacao` | Contract created before loan application |
| `test_relational_financial_logic` | `propostas`, `operacoes` | `operacoes.valor_contratado <= propostas.valor_solicitado`<br>`saldo_devedor <= valor_contratado` | Disbursed loan greater than requested amount |
| `test_approved_proposals_filter` | `operacoes`, `propostas` | `operacoes.proposta_id` only links to `propostas` where `status == 'APROVADA'` | Booked loan against rejected/pending proposal |
| `test_seed_determinism` | All tables | Re-running with `seed=42` produces identical DataFrames | Generator is non-deterministic |

### 4.3 Multi-Format Data Export Specifications

The export module supports three primary data persistence formats:

#### 1. CSV (Comma Separated Values)
- Target path: `output/datasets/csv/{table_name}.csv`
- Format specification: RFC 4180 compliant, UTF-8 encoding, comma delimiter, standard quotes for strings with special characters, ISO 8601 strings for timestamps (`YYYY-MM-DDTHH:MM:SS`), index excluded.
- Engine: `pandas.DataFrame.to_csv(..., index=False, encoding='utf-8')`.

#### 2. JSON (JavaScript Object Notation)
- Target path: `output/datasets/json/{table_name}.json`
- Format specification: Array of records (`orient="records"`), 2-space indentation, UTF-8 without ASCII escaping (`force_ascii=False`), ISO 8601 timestamps.
- Engine: `pandas.DataFrame.to_json(..., orient="records", indent=2, force_ascii=False, date_format="iso")`.

#### 3. Parquet (Columnar Storage)
- Target path: `output/datasets/parquet/{table_name}.parquet`
- Format specification: Apache Parquet format, Snappy compression (`compression='snappy'`), columnar dictionary encoding, native timestamp/decimal metadata preservation.
- Engine: `pyarrow` engine (`df.to_parquet(..., engine='pyarrow', compression='snappy', index=False)`).
- Fallback: `fastparquet` if `pyarrow` is unavailable.

---

## 5. Sample Credit Mesh Contract Specification (R5)

### 5.1 Business Domain & Mesh Topology

The sample contract `contracts/exemplo_credito_mesh.yaml` defines a banking credit mesh with 4 interconnected entity tables:

```
┌────────────────────────┐
│        empresas        │
│ (Empresas Tomadoras)   │
└───────────┬────────────┘
            │ 1:N
            ▼
┌────────────────────────┐         1:N         ┌────────────────────────┐
│       propostas        │────────────────────▶│       garantias        │
│ (Pedidos de Crédito)   │                     │ (Colaterais Vinculados)│
└───────────┬────────────┘                     └────────────────────────┘
            │ 1:1 (Aprovadas)
            ▼
┌────────────────────────┐
│       operacoes        │
│ (Contratos Ativos)     │
└────────────────────────┘
```

### 5.2 Complete Contract Schema YAML (`contracts/exemplo_credito_mesh.yaml`)

```yaml
data_contract_version: "1.0.0"
domain: "credit_risk"
dataset_name: "credit_mesh_ecosystem"
description: "Data Contract for multi-table corporate credit mesh: empresas, propostas, garantias, and operacoes."
owner: "credit-engineering@mesh.internal"
locale: "pt_BR"
default_sample_size: 100

tables:
  - name: "empresas"
    description: "Tabela cadastral de empresas tomadoras de crédito no ecossistema mesh."
    primary_key: "empresa_id"
    sample_size: 100
    fields:
      - name: "empresa_id"
        type: "string"
        format: "uuid"
        description: "Identificador único global da empresa."
        constraints:
          primary_key: true
          nullable: false
          unique: true
      - name: "cnpj"
        type: "string"
        description: "Cadastro Nacional da Pessoa Jurídica no formato padrão brasileiro."
        faker: "cnpj"
        constraints:
          nullable: false
          unique: true
          regex: "^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$"
      - name: "razao_social"
        type: "string"
        description: "Razão social oficial da pessoa jurídica."
        faker: "company"
        constraints:
          nullable: false
      - name: "nome_fantasia"
        type: "string"
        description: "Nome comercial / fantasia da empresa."
        faker: "company_suffix"
        constraints:
          nullable: true
      - name: "data_fundacao"
        type: "date"
        description: "Data de fundação / constituição da empresa."
        constraints:
          nullable: false
          max: "now"
          format: "%Y-%m-%d"
      - name: "faturamento_anual"
        type: "decimal"
        description: "Faturamento bruto anual em Reais (BRL)."
        constraints:
          nullable: false
          min: 100000.00
          max: 100000000.00
      - name: "setor"
        type: "string"
        description: "Setor de atuação econômica da empresa."
        constraints:
          nullable: false
          enum: ["INDUSTRIA", "COMERCIO", "SERVICOS", "AGRONEGOCIO", "TECNOLOGIA"]
      - name: "score_credito"
        type: "integer"
        description: "Pontuação de crédito (bureau score) da empresa."
        constraints:
          nullable: false
          min: 0
          max: 1000
      - name: "status_cadastral"
        type: "string"
        description: "Situação cadastral perante a instituição financeira."
        constraints:
          nullable: false
          enum: ["ATIVO", "INATIVO", "RECUPERACAO_JUDICIAL"]

  - name: "propostas"
    description: "Solicitações de crédito formalizadas pelas empresas tomadoras."
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
        format: "uuid"
        description: "Identificador único da proposta de crédito."
        constraints:
          primary_key: true
          nullable: false
          unique: true
      - name: "empresa_id"
        type: "string"
        format: "uuid"
        description: "Chave estrangeira referenciando a empresa solicitante."
        constraints:
          nullable: false
          foreign_key: "empresas.empresa_id"
      - name: "data_solicitacao"
        type: "datetime"
        description: "Timestamp ISO da submissão da proposta de crédito."
        constraints:
          nullable: false
          min: "2024-01-01T00:00:00"
          max: "now"
      - name: "valor_solicitado"
        type: "decimal"
        description: "Valor do empréstimo solicitado em BRL."
        constraints:
          nullable: false
          min: 10000.00
          max: 10000000.00
      - name: "prazo_meses"
        type: "integer"
        description: "Prazo de amortização desejado em meses."
        constraints:
          nullable: false
          min: 6
          max: 120
      - name: "taxa_juros_mensal"
        type: "float"
        description: "Taxa de juros proposta ao mês (ex: 0.025 = 2.5% a.m.)."
        constraints:
          nullable: false
          min: 0.010
          max: 0.060
      - name: "finalidade"
        type: "string"
        description: "Destinação dos recursos do empréstimo."
        constraints:
          nullable: false
          enum: ["CAPITAL_GIRO", "EXPANSAO", "EQUIPAMENTOS", "REFINANCIAMENTO"]
      - name: "status"
        type: "string"
        description: "Status de análise e esteira da proposta."
        constraints:
          nullable: false
          enum: ["EM_ANALISE", "APROVADA", "REJEITADA", "CANCELADA"]

  - name: "garantias"
    description: "Colaterais, avalistas e garantias vinculados às propostas de crédito."
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
        format: "uuid"
        description: "Identificador único da garantia."
        constraints:
          primary_key: true
          nullable: false
          unique: true
      - name: "proposta_id"
        type: "string"
        format: "uuid"
        description: "Chave estrangeira referenciando a proposta vinculada."
        constraints:
          nullable: false
          foreign_key: "propostas.proposta_id"
      - name: "tipo_garantia"
        type: "string"
        description: "Instrumento ou bem em garantia."
        constraints:
          nullable: false
          enum: ["IMOVEL", "VEICULO", "RECEBIVEIS", "AVAL", "FIANCA_BANCARIA"]
      - name: "valor_avaliado"
        type: "decimal"
        description: "Valor do laudo de avaliação do bem/garantia em BRL."
        constraints:
          nullable: false
          min: 5000.00
          max: 20000000.00
      - name: "percentual_cobertura"
        type: "float"
        description: "Razão entre valor da garantia e valor da proposta."
        constraints:
          nullable: false
          min: 0.20
          max: 3.00
      - name: "descricao"
        type: "string"
        description: "Detalhamento e matrícula do bem/garantia."
        constraints:
          nullable: true
      - name: "status_avaliacao"
        type: "string"
        description: "Situação do laudo pericial da garantia."
        constraints:
          nullable: false
          enum: ["AVALIADA", "PENDENTE", "REJEITADA"]

  - name: "operacoes"
    description: "Contratos de crédito formalizados e desembolsados para propostas aprovadas."
    primary_key: "operacao_id"
    sample_size: 90
    foreign_keys:
      - field: "proposta_id"
        references_table: "propostas"
        references_field: "proposta_id"
        relationship_type: "one_to_one"
        filter_condition: "propostas.status == 'APROVADA'"
      - field: "empresa_id"
        references_table: "empresas"
        references_field: "empresa_id"
        relationship_type: "many_to_one"
    fields:
      - name: "operacao_id"
        type: "string"
        format: "uuid"
        description: "Identificador único do contrato/operação de crédito."
        constraints:
          primary_key: true
          nullable: false
          unique: true
      - name: "proposta_id"
        type: "string"
        format: "uuid"
        description: "Chave estrangeira apontando para a proposta aprovada."
        constraints:
          nullable: false
          unique: true
          foreign_key: "propostas.proposta_id"
      - name: "empresa_id"
        type: "string"
        format: "uuid"
        description: "Chave estrangeira da empresa contratante (consistente com proposta)."
        constraints:
          nullable: false
          foreign_key: "empresas.empresa_id"
      - name: "codigo_contrato"
        type: "string"
        description: "Código de referência externa do contrato bancário."
        constraints:
          nullable: false
          unique: true
          regex: "^OP-2026-\\d{6}$"
      - name: "data_contratacao"
        type: "datetime"
        description: "Data e hora de emissão da cédula de crédito (CCB)."
        constraints:
          nullable: false
          min: "2024-01-01T00:00:00"
      - name: "valor_contratado"
        type: "decimal"
        description: "Valor principal efetivamente contratado em BRL."
        constraints:
          nullable: false
          min: 10000.00
          max: 10000000.00
      - name: "saldo_devedor"
        type: "decimal"
        description: "Saldo devedor atualizado da operação em BRL."
        constraints:
          nullable: false
          min: 0.00
      - name: "numero_parcelas"
        type: "integer"
        description: "Quantidade total de parcelas contratadas."
        constraints:
          nullable: false
          min: 6
          max: 120
      - name: "parcelas_pagas"
        type: "integer"
        description: "Quantidade de parcelas já amortizadas."
        constraints:
          nullable: false
          min: 0
      - name: "status_operacao"
        type: "string"
        description: "Classificação da adimplência da operação."
        constraints:
          nullable: false
          enum: ["EM_DIA", "ATRASO", "LIQUIDADA", "INADIMPLENTE"]

business_rules:
  - id: "BR01_APROVACAO_OBRIGATORIA"
    description: "Apenas propostas com status 'APROVADA' podem originar uma linha em operacoes."
    rule: "operacoes.proposta_id IN propostas[propostas.status == 'APROVADA'].proposta_id"
  - id: "BR02_CRONOLOGIA_CONTRATUAL"
    description: "A data de contratação da operação deve ser posterior ou igual à data da solicitação da proposta."
    rule: "operacoes.data_contratacao >= propostas.data_solicitacao"
  - id: "BR03_LIMITE_CONTRATADO"
    description: "O valor contratado não pode exceder o valor solicitado na proposta de crédito."
    rule: "operacoes.valor_contratado <= propostas.valor_solicitado"
  - id: "BR04_SALDO_CONSISTENTE"
    description: "O saldo devedor atual não pode ultrapassar o valor contratado."
    rule: "operacoes.saldo_devedor <= operacoes.valor_contratado"
  - id: "BR05_AMORTIZACAO_LIMITADA"
    description: "O número de parcelas pagas não pode exceder o número total de parcelas da operação."
    rule: "operacoes.parcelas_pagas <= operacoes.numero_parcelas"
  - id: "BR06_CONSISTENCIA_EMPRESA"
    description: "A empresa associada à operação deve ser idêntica à empresa solicitante da respectiva proposta."
    rule: "operacoes.empresa_id == propostas[operacoes.proposta_id == propostas.proposta_id].empresa_id"
```

---

## 6. Comprehensive Feature Inventory & Acceptance Criteria Matrix

### 6.1 Feature Inventory

#### CLI Features (Typer + Rich)
1. **F-CLI-01: Entrypoint & Subcommands**: Unified CLI `simula` supporting `run`, `inspect`, `diagram`, `export`, `test`, `ui`.
2. **F-CLI-02: Contract Inspection**: `simula inspect` prints formatted Rich schema tables, field constraints, and FK relationships.
3. **F-CLI-03: Real-Time Spinner & Progress Bar**: Live spinner feedback during OpenRouter LLM inference and sandbox test execution.
4. **F-CLI-04: Episodic Memory Traceback Panel**: Red Rich panel rendering captured syntax and assertion tracebacks with code context during retries.
5. **F-CLI-05: Final Deliverables Summary**: Rich tree highlighting created artifacts (`generator.py`, `test_mock.py`, `.mmd`, datasets) and file sizes.
6. **F-CLI-06: Configurable Execution Flags**: Support for `--contract`, `--iterations`, `--output-dir`, `--format`, `--rows`, `--model`, `--seed`, `--verbose`.

#### Web UI Features (Streamlit)
7. **F-UI-01: Contract Studio & YAML Editor**: Direct upload or in-browser editing of contract YAML with syntax highlighting and schema validation.
8. **F-UI-02: Preset Contract Selector**: Dropdown to instantly load `contracts/exemplo_credito_mesh.yaml`.
9. **F-UI-03: Live CoALA State & Step Streaming**: Visual status container (`st.status`) providing real-time node execution updates without full page reloads.
10. **F-UI-04: Triad Memory Inspector**: Dedicated visual views for Procedural, Working, and Episodic Memory with traceback cards and reflections.
11. **F-UI-05: Interactive Mermaid ERD Viewer**: Mermaid diagram rendered via HTML component with responsive container and code export.
12. **F-UI-06: Code & Sandbox Verification View**: Side-by-side inspection of generated `generator.py` and `test_mock.py` with terminal test output.
13. **F-UI-07: Tabular Data Explorer**: Multi-table data preview with filtering, sorting, column profiling, and individual/bulk format downloads.

#### Deliverables & Data Export Features
14. **F-EXP-01: Standalone Generator (`output/generator.py`)**: Zero agent dependency script executable via standard Python interpreter.
15. **F-EXP-02: Topological Dependency Ordering**: Generator resolves DAG table dependencies to guarantee parent records exist before children.
16. **F-EXP-03: Referential Integrity Enforcement**: Foreign keys drawn strictly from existing parent primary keys; zero orphaned records.
17. **F-EXP-04: Comprehensive Test Suite (`output/test_mock.py`)**: Suite validating schema, primary key uniqueness, referential integrity, nullability, enums, value ranges, and cross-table rules.
18. **F-EXP-05: Tri-Format Dataset Export**: Full dataset export in CSV, JSON (records), and Parquet (snappy pyarrow) to `output/datasets/{format}/{table}.{format}`.
19. **F-EXP-06: Reproducible Determinism**: Seed parameter (`--seed`) ensures byte-for-byte identical dataset generation across runs.

### 6.2 CLI Flag Matrix

| Flag | Short | Default | Type | Commands | Description |
|---|---|---|---|---|---|
| `--contract` | `-c` | *(Positional)* | `Path` | `run`, `inspect`, `diagram` | Path to contract YAML file |
| `--iterations` | `-m` | `5` | `int` | `run` | Maximum CoALA feedback iterations |
| `--output-dir` | `-o` | `output/` | `Path` | `run`, `export` | Output directory for all generated artifacts |
| `--rows` | `-n` | `100` | `int` | `run`, `export` | Sample size / row count for root tables |
| `--format` | `-f` | `csv,json,parquet` | `str` | `run`, `export` | Comma-separated list of formats (`csv`, `json`, `parquet`, `all`) |
| `--model` | none | `deepseek/deepseek-chat` | `str` | `run` | OpenRouter model identifier |
| `--seed` | `-s` | `42` | `int` | `run`, `export` | Random seed for deterministic generation |
| `--verbose` | `-v` | `False` | `bool` | `run`, `test` | Enable detailed debug logs & full tracebacks |
| `--no-diagram` | none | `False` | `bool` | `run` | Skip Mermaid ER diagram generation |
| `--port` | `-p` | `8501` | `int` | `ui` | Port for Streamlit Web UI server |
| `--host` | `-h` | `0.0.0.0` | `str` | `ui` | Host binding for Streamlit Web UI server |
| `--timeout` | `-t` | `30` | `int` | `test` | Subprocess execution timeout in seconds |

### 6.3 Streamlit UI Component Inventory

| Component ID | UI Container / Location | Streamlit Widget | Purpose |
|---|---|---|---|
| `UI-SIDE-01` | Sidebar | `st.text_input(type="password")` | OpenRouter API Key input |
| `UI-SIDE-02` | Sidebar | `st.selectbox` | Model selection (`deepseek-chat`, `deepseek-r1`) |
| `UI-SIDE-03` | Sidebar | `st.slider(min_value=1, max_value=10)` | Maximum iterations slider |
| `UI-SIDE-04` | Sidebar | `st.slider(min_value=10, max_value=5000)` | Row count multiplier slider |
| `UI-SIDE-05` | Sidebar | `st.multiselect` | Export format selection (`CSV`, `JSON`, `Parquet`) |
| `UI-SIDE-06` | Sidebar | `st.button("Run Simulation", type="primary")` | Trigger autonomous CoALA loop |
| `UI-TAB1-01` | Tab 1: Contract Studio | `st.file_uploader` | Upload custom contract YAML |
| `UI-TAB1-02` | Tab 1: Contract Studio | `st.selectbox` | Select preset contract (e.g. `exemplo_credito_mesh.yaml`) |
| `UI-TAB1-03` | Tab 1: Contract Studio | `st.text_area` / `st_ace` | Edit contract YAML with live validation |
| `UI-TAB1-04` | Tab 1: Contract Studio | `st.expander` + `st.table` | Schema tree view showing tables and fields |
| `UI-TAB2-01` | Tab 2: Agent Monitor | `st.status("Running CoALA Loop...")` | Live execution spinner and step logger |
| `UI-TAB2-02` | Tab 2: Agent Monitor | `st.columns(3)` (`st.metric`) | Iterations count, sandbox latency, loop status |
| `UI-TAB2-03` | Tab 2: Agent Monitor | `st.accordion("Episodic Memory History")` | Expandable cards for failed iterations and tracebacks |
| `UI-TAB2-04` | Tab 2: Agent Monitor | `st.expander("Procedural & Working Memory")` | Rules injected and current candidate prompt inspection |
| `UI-TAB3-01` | Tab 3: Mermaid ERD | `st.components.v1.html` | Interactive Mermaid ER diagram canvas |
| `UI-TAB3-02` | Tab 3: Mermaid ERD | `st.code(..., language="mermaid")` | Raw Mermaid `.mmd` syntax code |
| `UI-TAB3-03` | Tab 3: Mermaid ERD | `st.download_button` | Download `.mmd` file |
| `UI-TAB4-01` | Tab 4: Generated Code | `st.tabs(["generator.py", "test_mock.py"])` | Syntax-highlighted code viewers |
| `UI-TAB4-02` | Tab 4: Generated Code | `st.code(..., language="bash")` | Pytest sandbox console output & test report |
| `UI-TAB5-01` | Tab 5: Data Preview | `st.selectbox` | Select active table to inspect |
| `UI-TAB5-02` | Tab 5: Data Preview | `st.dataframe` | Interactive tabular data view with sort/filter |
| `UI-TAB5-03` | Tab 5: Data Preview | `st.columns(3)` (`st.download_button`) | Direct download buttons for CSV, JSON, Parquet |
| `UI-TAB5-04` | Tab 5: Data Preview | `st.download_button` | Download complete datasets ZIP bundle |

### 6.4 Acceptance Criteria & Verification Matrix

- [ ] **AC-01: CLI Execution & Rich Rendering**: Running `simula run contracts/exemplo_credito_mesh.yaml` displays a header banner, shows animated spinners during execution, and prints a final artifact tree upon completion.
- [ ] **AC-02: Standalone Generator Independence**: `python output/generator.py --rows 50 --output-dir output/datasets --format all` runs cleanly without requiring LangGraph, OpenRouter, or internal simula modules.
- [ ] **AC-03: Multi-Format Data Output**: Datasets are successfully created in `output/datasets/csv/`, `output/datasets/json/`, and `output/datasets/parquet/` for all 4 tables (`empresas`, `propostas`, `garantias`, `operacoes`).
- [ ] **AC-04: Pytest Suite Conformance**: Running `pytest output/test_mock.py` against generated datasets exits with return code 0 and verifies schema, primary keys, foreign keys, nullability, and business rules.
- [ ] **AC-05: Referential Integrity**: Every `proposta_id` in `garantias` and `operacoes` matches a valid `proposta_id` in `propostas`; every `empresa_id` in `propostas` matches a valid `empresa_id` in `empresas`.
- [ ] **AC-06: Business Rules Compliance**: In generated mock data, all operations reference approved proposals, `data_contratacao >= data_solicitacao`, and `valor_contratado <= valor_solicitado`.
- [ ] **AC-07: Streamlit Dashboard Launch**: Executing `simula ui` or `streamlit run ui/app.py` loads without errors, allows uploading/selecting contracts, renders the Mermaid ER diagram, displays live execution status, and permits tabular dataset exploration.
- [ ] **AC-08: Deterministic Repeatability**: Executing `generator.py` twice with identical `--seed 42` produces identical row values and checksums across CSV, JSON, and Parquet.
