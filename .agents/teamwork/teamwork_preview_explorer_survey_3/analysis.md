# Technical Survey & Specification: Simula-AI (Explorer 3)
**Scope**: Hybrid Mermaid ER Diagram Generation (R3), Podman Containerization & Packaging (R5), Acceptance Criteria & E2E Testing Feasibility  
**Date**: 2026-10-12  
**Author**: Explorer 3 (Survey Phase)  

---

## 1. Executive Summary & Scope

Simula-AI is an autonomous relational data mocking framework for Data Mesh ecosystems. It ingests a data contract YAML and uses an iterative CoALA cognitive loop (LangGraph + OpenRouter DeepSeek) with an isolated Pytest sandbox to generate consistent Faker generators, validation test suites, exported datasets, and interactive Mermaid ER diagrams.

This survey establishes the complete technical specification for:
1. **Hybrid Mermaid ER Diagram Generation (R3)**: Deterministic extraction from contract YAML, semantic cardinality enrichment, rendering in Streamlit and CLI, and persistent export to `output/mesh_er_diagram.mmd`.
2. **Containerization with Podman & Packaging (R5)**: Rootless `Containerfile`, dual-mode `entrypoint.sh` (CLI + Streamlit UI), dependency management (`pyproject.toml`, `requirements.txt`), `.env.example`, and user-facing `README.md`.
3. **Acceptance Criteria & E2E Testing Feasibility**: Comprehensive acceptance matrix, opaque-box test harness design, test tiering (Tiers 1–5), and deterministic mock LLM strategy for offline CI/CD testability.

---

## 2. Hybrid Mermaid ER Diagram Generation (R3)

### 2.1 Problem & Architectural Strategy

A Data Mesh contract defines schema metadata (domain, tables, columns, constraints, foreign keys). Converting this into an Entity-Relationship (ER) diagram requires two distinct layers:
1. **Deterministic Layer (Structural Truth)**: Extracts tables, columns, primary keys (`PK`), unique keys (`UK`), and foreign keys (`FK`) with 100% mathematical fidelity directly from YAML. Never hallucinates column names or types.
2. **Semantic Layer (Relational Rules)**: Enriches standard foreign key connections with domain-specific cardinality markers (`||--o{`, `||--||`, `||--|{`, `|o--o{`) and business action labels (e.g., `EMPRESAS ||--o{ PROPOSTAS : "submete"`).

A purely LLM-generated diagram risks syntax errors or hallucinated schemas. A purely deterministic diagram lacks rich semantic business cardinality if not explicitly declared in the YAML. The **Hybrid Pattern** combines both: deterministic extraction establishes the valid syntactic baseline, while semantic annotations (from contract metadata or cognitive agent enrichment) enrich the relationship edges.

### 2.2 Mermaid ER Diagram Syntax & Rules

Mermaid ER diagrams follow strict formal grammar:
- **Header**: Must start with `erDiagram` on its own line.
- **Entity Block**:
  ```mermaid
  erDiagram
      EMPRESAS {
          string id_empresa PK "Chave primaria"
          string cnpj UK "Cadastro de Pessoa Juridica"
          string razao_social "Nome empresarial"
          date data_fundacao "Data de constituicao"
          float faturamento_anual "Faturamento anual declarado"
      }
  ```
- **Syntax Rules**:
  - Entity names: Alphanumeric and underscores, no spaces (e.g. `EMPRESAS`, `PROPOSTAS_CREDITO`).
  - Attribute line: `<type> <name> [<key_type>] ["<comment>"]`.
  - Allowed `<key_type>` values: `PK`, `FK`, `UK`.
  - Type sanitization: Types in SQL/YAML like `varchar(255)`, `decimal(10,2)`, `timestamp without time zone` must be sanitized to valid alphanumeric identifiers (e.g., `varchar`, `decimal`, `timestamp`), removing parentheses and spaces to avoid Mermaid syntax parse errors.
  - Comments: Must be enclosed in double quotes `"` and escaped if containing quotes.

- **Relationship Syntax**:
  `<entity1> <left_cardinality><line><right_cardinality> <entity2> : "<label>"`
  - Line style: `--` (solid, standard) or `..` (dashed, non-identifying). Standard recommendation: `--`.
  - Cardinality markers:
    | Left | Right | Meaning |
    | :--- | :--- | :--- |
    | `\|\|` | `\|\|` | Exactly one to Exactly one (1:1 mandatory) |
    | `\|\|` | `o\|` / `\|o` | Exactly one to Zero or one (1:0..1 optional) |
    | `\|\|` | `o{` / `}o` | Exactly one to Zero or many (1:N optional) |
    | `\|\|` | `\|{` / `\}\|` | Exactly one to One or many (1:N mandatory) |
    | `\|o` | `o{` / `}o` | Zero or one to Zero or many (0..1:N) |
    | `\}o` | `o\{` | Many to Many (N:M optional) |
    | `\}\|` | `\|\{` | Many to Many (N:M mandatory) |

### 2.3 Semantic Cardinality Inference Heuristic Matrix

When contract YAML specifies foreign keys without explicit cardinality, the deterministic extractor applies this inference matrix:

| FK Column Constraints | Target Table PK Nullable? | Inferred Cardinality Symbol | Domain Meaning | Default Label |
| :--- | :--- | :--- | :--- | :--- |
| `nullable: false`, `unique: false` | No (PK is mandatory) | `PARENT \|\|--o{ CHILD` | One parent has zero or more children | `"possui"` / `"relaciona"` |
| `nullable: false`, `unique: true` | No | `PARENT \|\|--\|\|` or `PARENT \|\|--o\| CHILD` | Strict 1-to-1 or 1-to-0..1 | `"associado_a"` |
| `nullable: true`, `unique: false` | No | `PARENT \|o--o{ CHILD` | Optional parent to zero or more children | `"opcionalmente_possui"` |
| `nullable: true`, `unique: true` | No | `PARENT \|o--o\| CHILD` | Optional 1-to-1 | `"opcionalmente_associa"` |

If the contract YAML explicitly contains `cardinality` (e.g. `one_to_many`, `many_to_one`, `one_to_one`) or `relationship_label` (e.g. `submete`, `garante`), or if the cognitive agent enriches the relationships in `working_memory`, the generator overrides the heuristic with the explicit semantic cardinality.

### 2.4 Extractor Architecture (`core/diagram.py`)

```python
# Conceptual Architecture for core/diagram.py
import re
from typing import Any, Dict, List, Optional
from pathlib import Path

class MermaidERGenerator:
    """Deterministic and hybrid Mermaid ER diagram generator for Data Mesh contracts."""
    
    @staticmethod
    def sanitize_type(field_type: str) -> str:
        """Strip parameters like (255) and illegal characters from types."""
        cleaned = re.sub(r'\(.*?\)', '', str(field_type).strip())
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned)
        return cleaned.lower() or "string"

    @staticmethod
    def sanitize_entity(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_]', '_', name).upper()

    def generate(self, contract: Dict[str, Any], semantic_enrichments: Optional[Dict[str, Any]] = None) -> str:
        """
        Extracts tables, columns, PKs, FKs deterministically.
        Applies semantic cardinalities if provided in contract or semantic_enrichments.
        Returns valid Mermaid erDiagram code.
        """
        lines = ["erDiagram"]
        tables = contract.get("tables", [])
        
        # 1. Deterministic extraction of entities & attributes
        for table in tables:
            tname = self.sanitize_entity(table.get("name", "TABLE"))
            pks = set(table.get("primary_key", []))
            fks = {fk.get("field") for fk in table.get("foreign_keys", []) if "field" in fk}
            
            lines.append(f"    {tname} {{")
            for field in table.get("fields", []):
                fname = field.get("name", "col")
                ftype = self.sanitize_type(field.get("type", "string"))
                
                key_type = ""
                if fname in pks:
                    key_type = "PK"
                elif fname in fks:
                    key_type = "FK"
                elif field.get("unique", False):
                    key_type = "UK"
                
                desc = field.get("description", "").replace('"', "'")
                comment = f' "{desc}"' if desc else ""
                
                key_part = f" {key_type}" if key_type else ""
                lines.append(f"        {ftype} {fname}{key_part}{comment}")
            lines.append("    }")

        # 2. Relationship extraction & semantic enrichment
        for table in tables:
            child_name = self.sanitize_entity(table.get("name", ""))
            for fk in table.get("foreign_keys", []):
                ref = fk.get("references", {})
                parent_table = ref.get("table", "")
                if not parent_table:
                    continue
                parent_name = self.sanitize_entity(parent_table)
                
                # Check semantic enrichments or contract metadata
                rel_key = f"{parent_name}->{child_name}"
                enrichment = (semantic_enrichments or {}).get(rel_key, {})
                
                cardinality = enrichment.get("cardinality") or fk.get("cardinality", "||--o{")
                label = enrichment.get("label") or fk.get("relationship_name") or fk.get("field", "references")
                
                lines.append(f'    {parent_name} {cardinality} {child_name} : "{label}"')
                
        return "\n".join(lines) + "\n"

    def save(self, mmd_content: str, output_path: str = "output/mesh_er_diagram.mmd") -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mmd_content, encoding="utf-8")
        return out
```

### 2.5 Multi-Target Rendering

#### A. Streamlit Web UI Rendering
Streamlit core does not include native `st.mermaid()`. The recommended, zero-dependency, bulletproof technique embeds Mermaid.js via Streamlit HTML component (`streamlit.components.v1.html`):
```python
import streamlit as st
import streamlit.components.v1 as components

def render_mermaid_ui(mmd_code: str, height: int = 520):
    html_payload = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{
          startOnLoad: true,
          theme: 'neutral',
          er: {{ useMaxWidth: true }}
        }});
      </script>
      <style>
        body {{ margin: 0; padding: 10px; background: transparent; font-family: sans-serif; }}
        .mermaid {{ display: flex; justify-content: center; }}
      </style>
    </head>
    <body>
      <div class="mermaid">
        {mmd_code}
      </div>
    </body>
    </html>
    """
    components.html(html_payload, height=height, scrolling=True)
    
    with st.expander("📄 Ver Código Mermaid (.mmd)"):
        st.code(mmd_code, language="mermaid")
        st.download_button(
            label="⬇️ Baixar Diagrama (mesh_er_diagram.mmd)",
            data=mmd_code,
            file_name="mesh_er_diagram.mmd",
            mime="text/vnd.mermaid"
        )
```
- **Advantages**: 100% SVG client-side rendering; no npm binaries or headless Chrome (puppeteer) required on the server/container; responsive layout; native download button.

#### B. CLI Terminal Output
In the CLI (`cli/main.py`), using Typer and Rich:
```python
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

def display_terminal_diagram(mmd_code: str, raw: bool = False):
    if raw:
        print(mmd_code)
    else:
        syntax = Syntax(mmd_code, "mermaid", theme="monokai", line_numbers=True)
        console.print(Panel(
            syntax,
            title="[bold green]Mermaid ER Diagram (output/mesh_er_diagram.mmd)[/bold green]",
            subtitle="[dim]Tip: view in Streamlit or pipe to mermaid-cli for SVG/PNG[/dim]",
            border_style="green"
        ))
```

#### C. File Persistence
- Stored deterministically at `output/mesh_er_diagram.mmd`.
- Automatically created whenever the CLI runs or contract is loaded in UI.

---

## 3. Containerization with Podman & Packaging (R5)

### 3.1 Rootless Podman Architecture

Podman runs rootless containers by mapping the container's unprivileged user namespace to the user's host UID. Standard container best practices require:
1. **Unprivileged UID/GID**: Run as non-root user (e.g. `UID 10001:10001`, user `simula`).
2. **Directory Ownership**: Pre-create `/app`, `/app/output`, `/app/contracts` and set ownership to `simula:simula`.
3. **Ports**: Listen on port `8501` (> 1024).
4. **Volume Mounting with SELinux / Permissions**: When running with Podman on Linux, volume mounts use `:Z` flag (e.g. `-v ./output:/app/output:Z`) to configure SELinux labels properly.
5. **No Systemd Daemon Dependency**: Pure OCI container executing either Streamlit or Typer CLI directly via exec.

### 3.2 Rootless `Containerfile` Specification

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

# System environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/simula \
    PATH="/home/simula/.local/bin:$PATH"

# Install system dependencies (curl for healthcheck, ca-certificates for OpenRouter HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged non-root user and group
RUN groupadd -g 10001 simula && \
    useradd -u 10001 -g simula -m -d /home/simula -s /bin/bash simula

# Working directory setup
WORKDIR /app
RUN mkdir -p /app/output /app/contracts /app/ui /app/core /app/cli && \
    chown -R simula:simula /app /home/simula

# Install dependencies as user to ensure isolated environment
COPY --chown=simula:simula requirements.txt pyproject.toml /app/
USER simula
RUN pip install --user --no-cache-dir -r requirements.txt

# Copy source code and scripts
COPY --chown=simula:simula . /app/
RUN chmod +x /app/entrypoint.sh

# Web UI port
EXPOSE 8501

# Container healthcheck for Streamlit
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["streamlit"]
```

### 3.3 Container Entrypoint (`entrypoint.sh`)

`entrypoint.sh` allows single container image to serve CLI, Streamlit UI, or pytest test suites:

```bash
#!/usr/bin/env bash
set -e

# Ensure output directory exists and is writable
mkdir -p /app/output

case "$1" in
    streamlit|web|ui)
        echo "Starting Simula-AI Streamlit Web UI on port 8501..."
        exec streamlit run ui/app.py \
            --server.port=8501 \
            --server.address=0.0.0.0 \
            --server.headless=true
        ;;
    cli)
        shift
        exec python -m cli.main "$@"
        ;;
    test)
        shift
        exec pytest "$@"
        ;;
    *)
        # Fallback to direct command execution
        exec "$@"
        ;;
esac
```

### 3.4 Python Packaging & Dependencies Management

We specify both standard modern PEP 621 `pyproject.toml` and clean `requirements.txt`.

#### `requirements.txt`
```text
# Cognitive Loop & State (LangGraph + OpenRouter)
langgraph>=0.2.20,<0.3.0
langchain-core>=0.3.0,<0.4.0
httpx>=0.27.0
openai>=1.40.0
pydantic>=2.7.0,<3.0.0
pyyaml>=6.0.1
python-dotenv>=1.0.1

# Synthetic Mocking & Validation
faker>=25.0.0
pytest>=8.2.0

# Data Export Engines
pandas>=2.2.0
pyarrow>=16.0.0
fastparquet>=2024.5.0

# User Interfaces (CLI & Web UI)
typer>=0.12.0
rich>=13.7.0
streamlit>=1.35.0

# Development & Testing
pytest-cov>=5.0.0
pytest-mock>=3.14.0
```

#### `pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "simula-ai"
version = "0.1.0"
description = "Autonomous relational data mocking framework for Data Mesh ecosystems"
readme = "README.md"
requires-python = ">=3.11"
authors = [{ name = "Simula-AI Team" }]
license = { text = "MIT" }
dependencies = [
    "langgraph>=0.2.20,<0.3.0",
    "langchain-core>=0.3.0,<0.4.0",
    "httpx>=0.27.0",
    "openai>=1.40.0",
    "pydantic>=2.7.0",
    "pyyaml>=6.0.1",
    "python-dotenv>=1.0.1",
    "faker>=25.0.0",
    "pytest>=8.2.0",
    "pandas>=2.2.0",
    "pyarrow>=16.0.0",
    "fastparquet>=2024.5.0",
    "typer>=0.12.0",
    "rich>=13.7.0",
    "streamlit>=1.35.0",
]

[project.optional-dependencies]
dev = [
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.4.0",
]

[project.scripts]
simula = "cli.main:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --tb=short"
```

### 3.5 Environment Variables & Configuration (`.env.example`)

```bash
# OpenRouter API Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=deepseek/deepseek-r1
OPENROUTER_FALLBACK_MODEL=deepseek/deepseek-chat

# Cognitive Loop Tuning
SIMULA_MAX_ITERATIONS=5
SIMULA_SANDBOX_TIMEOUT_SECONDS=30
SIMULA_LOG_LEVEL=INFO

# Streamlit Configuration
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
STREAMLIT_SERVER_HEADLESS=true

# Mock Mode (For Offline E2E Testing without live LLM tokens)
SIMULA_MOCK_LLM=false
```

### 3.6 README.md Blueprint

The project `README.md` must include:
1. **Title & Badge Header**: Simula-AI banner, Python 3.11+, Podman Ready.
2. **Overview**: Description of autonomous data contract mocking via CoALA cognitive loop.
3. **Architecture Diagram**: Contract YAML -> LangGraph (CoALA) -> DeepSeek R1 -> Pytest Sandbox -> Artifacts (`generator.py`, `test_mock.py`, CSV/JSON/Parquet, `mesh_er_diagram.mmd`).
4. **Quickstart (Local)**:
   ```bash
   git clone <repo> && cd simula-ai
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # set OPENROUTER_API_KEY
   ```
5. **CLI Usage**:
   ```bash
   # Run full cognitive loop on credit mesh contract
   python -m cli.main run contracts/exemplo_credito_mesh.yaml

   # Generate and inspect Mermaid ER diagram
   python -m cli.main diagram contracts/exemplo_credito_mesh.yaml
   ```
6. **Streamlit Web UI**:
   ```bash
   streamlit run ui/app.py
   # Opens http://localhost:8501
   ```
7. **Podman Container Usage**:
   ```bash
   # Build container image
   podman build -t simula-ai .

   # Run Streamlit Web UI (mount output directory)
   podman run -d --name simula-ui -p 8501:8501 \
       --env-file .env \
       -v ./output:/app/output:Z \
       simula-ai streamlit

   # Run CLI in ephemeral container
   podman run --rm \
       --env-file .env \
       -v ./contracts:/app/contracts:Z \
       -v ./output:/app/output:Z \
       simula-ai cli run contracts/exemplo_credito_mesh.yaml
   ```
8. **Sample Credit Mesh Contract**: Overview of `contracts/exemplo_credito_mesh.yaml` (empresas, propostas, garantias, operacoes).
9. **Testing & Quality Assurance**:
   ```bash
   pytest tests/
   ```

---

## 4. Acceptance Criteria & E2E Testing Feasibility

### 4.1 Complete Acceptance Checklist Mapping

| Requirement | Acceptance Criterion | Verification Method | Pass Condition |
| :--- | :--- | :--- | :--- |
| **R1 (CoALA Loop)** | Subprocess sandbox runs in isolation with strict timeout | Subprocess test with infinite loop (`while True: pass`) | Process terminates in <= 30s, returns timeout error code, zero `eval()` used |
| **R1 (CoALA Loop)** | Strips `<think>...</think>` from DeepSeek R1 | Unit test regex extractor with varied think blocks & edge cases | Extracted code is pure Python, free of think tags and markdown markers |
| **R1 (CoALA Loop)** | Feedback loop injects tracebacks into `episodic_memory` | Multi-iteration test with intentional bug in iteration 0 | `episodic_memory` contains iteration 0 traceback, prompt in iteration 1 contains error history |
| **R2 (CLI)** | Typer CLI loads contract and executes full loop | Typer `CliRunner` invoking `run contracts/exemplo_credito_mesh.yaml` | Exit code 0, prints Rich progress/spinner, generates artifacts |
| **R2 (Streamlit)** | Streamlit interface boots cleanly and displays contract + diagram | Headless probe `curl -f http://localhost:8501/_stcore/health` and AppTest | HTTP 200 health check, contract rendered, diagram rendered |
| **R3 (Mermaid ER)** | Deterministic extraction of all tables, fields, PKs, FKs | Schema comparison test between YAML and generated `.mmd` | All 4 tables present, PK/FK markers match, valid Mermaid syntax |
| **R3 (Mermaid ER)** | Semantic cardinality annotations | Check output for relational markers | Contains `||--o{`, `||--||`, etc., and domain labels |
| **R3 (Mermaid ER)** | Exported to `output/mesh_er_diagram.mmd` | File existence and non-empty check | File exists at exact path, starts with `erDiagram` |
| **R4 (Export)** | Standalone generator `output/generator.py` | Executed directly: `python output/generator.py` | Exit code 0, outputs valid datasets |
| **R4 (Export)** | Standalone pytest suite `output/test_mock.py` | Executed directly: `pytest output/test_mock.py` | Exit code 0, all tests pass |
| **R4 (Export)** | Datasets in CSV, JSON, Parquet in `output/datasets/` | File inspection and schema verification with pandas | Non-empty files present for all 4 tables in all 3 formats |
| **R5 (Container)** | `podman build -t simula-ai .` succeeds | Opaque-box build command test | Build completes with returncode 0 |
| **R5 (Container)** | Rootless container run | `podman run --rm simula-ai cli --help` | Exit code 0, displays CLI help |
| **R5 (Config)** | `.env.example` and `README.md` present | File check | Files exist with all required sections |

### 4.2 Opaque-Box E2E Test Harness Strategy

To guarantee E2E testability without relying on external network connectivity or burning live LLM tokens in CI, we design a **Deterministic Mock Provider Pattern** integrated directly into the framework:

1. **Dual-Mode LLM Gateway (`core/llm_client.py`)**:
   - Checks `os.getenv("SIMULA_MOCK_LLM", "false").lower() == "true"`.
   - In Live Mode: Calls OpenRouter `https://openrouter.ai/api/v1/chat/completions` with DeepSeek R1 / chat.
   - In Mock Mode: Returns scripted responses containing `<think>Reasoning...</think> ```python ... ````.
2. **Two-Stage Failure-Recovery Mock**:
   - When configured for recovery testing, mock returns a failing test script on Call #1 (e.g. `assert len(df) == 100` where only 10 rows generated).
   - Pytest sandbox runs, fails, captures traceback, logs to `episodic_memory`.
   - On Call #2, mock detects `episodic_memory` has error traceback and returns the corrected script!
   - Sandbox runs, passes with returncode 0.
   - Loop terminates and writes all R4 & R3 deliverables.
3. **Test Tiers (1 to 5)**:
   - **Tier 1 (Unit)**: Regex extraction, YAML schema parser, Mermaid ER generator, State transitions.
   - **Tier 2 (Sandbox Security)**: Timeout enforcement, subprocess isolation, zero `eval()` audit.
   - **Tier 3 (CLI & UI)**: CLI options via `CliRunner`, Streamlit import & component rendering.
   - **Tier 4 (Full E2E Loop)**: Mock-driven end-to-end run from contract ingestion to dataset exports and diagram verification.
   - **Tier 5 (Packaging & Container)**: `podman build` test and rootless execution verification.

---

## 5. Proposed Project Layout & Interfaces

```
simula-ai/
├── contracts/
│   └── exemplo_credito_mesh.yaml   # Multi-table credit mesh contract (empresas, propostas, garantias, operacoes)
├── core/
│   ├── __init__.py
│   ├── state.py                    # SimulaState TypedDict (procedural, working, episodic)
│   ├── loop.py                     # LangGraph cognitive loop & conditional router
│   ├── llm_client.py               # OpenRouter DeepSeek client with 429 backoff & mock support
│   ├── parser.py                   # Regex <think> stripping & code extraction
│   ├── sandbox.py                  # Isolated Pytest subprocess runner (no eval, strict timeout)
│   ├── diagram.py                  # Deterministic + Semantic Mermaid ER Generator (R3)
│   └── exporter.py                 # Artifact exporter (generator.py, test_mock.py, datasets)
├── cli/
│   ├── __init__.py
│   └── main.py                     # Typer CLI with Rich spinners & formatting
├── ui/
│   ├── __init__.py
│   └── app.py                      # Streamlit Web UI with Mermaid rendering & state inspection
├── tests/
│   ├── test_diagram.py             # Mermaid generator tests
│   ├── test_parser.py              # Regex parser tests
│   ├── test_sandbox.py             # Sandbox subprocess & timeout tests
│   ├── test_loop.py                # CoALA cognitive loop tests
│   ├── test_cli.py                 # CLI integration tests
│   └── test_e2e.py                 # Full pipeline E2E tests
├── output/                         # Target artifact directory (.gitignore except .gitkeep)
│   ├── mesh_er_diagram.mmd
│   ├── generator.py
│   ├── test_mock.py
│   └── datasets/
├── Containerfile                   # Rootless Podman container build recipe
├── entrypoint.sh                   # Dual-mode container entrypoint
├── requirements.txt                # Pinned runtime dependencies
├── pyproject.toml                  # Python package configuration
├── .env.example                    # Template environment variables
└── README.md                       # Comprehensive documentation
```
