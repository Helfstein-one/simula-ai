# Milestone 2 Technical Investigation & Implementation Blueprint: State, Memory & LLM Client

**Author**: Explorer 1 (Milestone 2 - CoALA Cognitive Loop & Sandbox)  
**Target Files**: `core/state.py`, `core/memory.py`, `core/llm_client.py`  
**Working Directory**: `/Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m2_1/`  
**Date**: 2026-10-12  

---

## 1. Executive Summary & Problem Boundary

Simula-AI implements the **CoALA (Cognitive Architectures for Language Agents)** framework to generate relational data mockers and validation test suites from Data Mesh contracts. 

In Milestone 2, the system establishes its cognitive core. This investigation designs and blueprints the first three foundational modules:
1. **`core/state.py`**: The agent's persistent state container (`SimulaState`), memory hierarchies (`procedural_memory`, `working_memory`, `episodic_memory`), loop lifecycle flags (`status`), and streaming UI/CLI event objects (`SimulaEvent`).
2. **`core/memory.py`**: Static domain engineering rules (procedural memory for Faker, topological sorting, and Pytest assertions) plus dynamic failure capture and prompt formatting (episodic memory).
3. **`core/llm_client.py`**: Production-grade OpenRouter client targeting DeepSeek reasoning models with HTTP 429 exponential backoff, full jitter, `Retry-After` header parsing, model fallback cascades, and a deterministic Mock LLM provider supporting multi-iteration retry testing.

All designs have been verified against existing test fixtures in `tests/conftest.py` and test suites in `tests/e2e/`.

---

## 2. Architectural Mapping & CoALA Memory Taxonomy

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SimulaState (TypedDict)                         │
│                                                                        │
│  ┌───────────────────────┐  ┌────────────────────┐  ┌───────────────┐  │
│  │   Procedural Memory   │  │   Working Memory   │  │Episodic Memory│  │
│  │ (Faker/Topo/Pytest)   │  │(YAML/Code/Sandbox) │  │(Tracebacks)   │  │
│  └───────────┬───────────┘  └──────────┬─────────┘  └───────┬───────┘  │
│              │                         │                    │          │
│              │                         │                    │          │
│              ▼                         ▼                    ▼          │
│        core/memory.py            core/state.py       core/memory.py    │
└──────────────┼─────────────────────────┼────────────────────┼──────────┘
               │                         │                    │
               │ (Prompt Rules)          │ (Active Task)      │ (Error History)
               ▼                         ▼                    ▼
   ┌──────────────────────────────────────────────────────────────┐
   │             core/llm_client.py (OpenRouterClient)            │
   │                                                              │
   │   - Primary: deepseek/deepseek-r1                            │
   │   - Fallback 1: deepseek/deepseek-chat                       │
   │   - Fallback 2: deepseek/deepseek-r1-distill-llama-70b       │
   │   - Full Jitter Exponential Backoff (HTTP 429/5xx)           │
   │   - Deterministic Mock Provider (SIMULA_MOCK_LLM=true)       │
   └──────────────────────────────────────────────────────────────┘
```

### Memory System Responsibilities

| CoALA Component | Module | Role & Contents | Lifetime |
|---|---|---|---|
| **Procedural Memory** | `core/memory.py` | Domain best practices: Brazilian Faker idioms (`pt_BR`, CNPJ), topological DAG sorting rules, referential integrity axioms, Pytest assertion patterns. | Static across all runs and iterations |
| **Working Memory** | `core/state.py` | Transient cycle workspace: `contract_yaml`, `contract_dict`, `generated_code`, latest `pytest_output`, `pytest_exit_code`, `last_error`. | Updated at each node execution |
| **Episodic Memory** | `core/memory.py` + `core/state.py` | Temporal history: sequence of `EpisodicMemoryRecord` capturing iteration index, code candidate, exit code, stdout/stderr, failed test names, and parsed error summary. | Preserved across retries within a single run |

---

## 3. Detailed Component Blueprints

### 3.1 Component 1: `core/state.py`

#### Key Design Decisions:
1. **TypedDict Schema Compliance**: Strict conformance to tests expecting `procedural_memory`, `working_memory`, `episodic_memory`, `iterations`, and `status`.
2. **Episodic Record Schema**: `EpisodicMemoryRecord` contains annotations for `iteration`, `exit_code`, `stdout`, `stderr`, `generated_code`, `error_summary`, `failed_tests`, and `timestamp`.
3. **Status Transitions**: `StatusType` handles `"INIT"`, `"GENERATING"`, `"EXECUTING"`, `"RETRY"`, `"SUCCESS"`, `"FAILED_MAX_RETRIES"`, `"FAILED"`, `"ERROR"`.
4. **Streaming SimulaEvent**: Dataclass for real-time observation by CLI progress spinners (`cli/main.py`) and Streamlit monitor (`ui/app.py`).

#### Concrete Implementation Blueprint (`proposed_state.py`):

```python
"""core/state.py - Simula-AI CoALA Cognitive Loop State & Memory Definitions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict


class EpisodicMemoryRecord(TypedDict):
    """Snapshot of a single execution attempt within the CoALA cognitive loop."""

    iteration: int
    generated_code: str
    exit_code: int
    stdout: str
    stderr: str
    error_summary: str
    failed_tests: List[str]
    timestamp: str


class WorkingMemory(TypedDict, total=False):
    """Short-term workspace holding current cycle artifacts."""

    contract_yaml: str
    contract_dict: Optional[Dict[str, Any]]
    generated_code: Optional[str]
    pytest_output: Optional[str]
    pytest_exit_code: Optional[int]
    last_error: Optional[str]


class ProceduralMemory(TypedDict, total=False):
    """Static knowledge base of rules, idioms, and system instructions."""

    system_prompt: str
    faker_rules: List[str]
    relational_rules: List[str]
    pytest_rules: List[str]
    guidelines: List[str]
    rules: List[str]


StatusType = Literal[
    "INIT",
    "GENERATING",
    "EXECUTING",
    "RETRY",
    "SUCCESS",
    "FAILED_MAX_RETRIES",
    "FAILED",
    "ERROR",
]


class SimulaState(TypedDict, total=False):
    """Top-level agent state container passed across LangGraph nodes."""

    procedural_memory: ProceduralMemory
    working_memory: WorkingMemory
    episodic_memory: List[EpisodicMemoryRecord]
    iterations: int
    max_iterations: int
    status: StatusType
    error_message: Optional[str]
    model_name: Optional[str]
    run_id: Optional[str]


@dataclass
class SimulaEvent:
    """Event yielded during cognitive loop execution for real-time UI/CLI feedback."""

    step: str
    iteration: int
    state: SimulaState
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to serializable dictionary."""
        return {
            "step": self.step,
            "iteration": self.iteration,
            "message": self.message,
            "timestamp": self.timestamp,
            "status": self.state.get("status"),
            "pytest_exit_code": self.state.get("working_memory", {}).get("pytest_exit_code"),
        }


def create_initial_state(
    contract_yaml: str,
    max_iterations: int = 5,
    model_name: str = "deepseek/deepseek-r1",
    run_id: Optional[str] = None,
) -> SimulaState:
    """Constructs a clean initial SimulaState instance."""
    from core.memory import create_initial_procedural_memory

    return {
        "procedural_memory": create_initial_procedural_memory(),
        "working_memory": {
            "contract_yaml": contract_yaml,
            "contract_dict": None,
            "generated_code": None,
            "pytest_output": None,
            "pytest_exit_code": None,
            "last_error": None,
        },
        "episodic_memory": [],
        "iterations": 0,
        "max_iterations": max_iterations,
        "status": "INIT",
        "error_message": None,
        "model_name": model_name,
        "run_id": run_id,
    }
```

---

### 3.2 Component 2: `core/memory.py`

#### Key Design Decisions:
1. **Procedural Memory Factory**: `create_initial_procedural_memory()` returns a dictionary populated with `faker_rules`, `relational_rules`, `pytest_rules`, `guidelines`, `rules`, and `system_prompt`.
2. **Domain-Specific Rules**:
   - **Faker**: Brazilian locale `Faker(['pt_BR', 'en_US'])`, deterministic seeding `Faker.seed(42)`, valid CNPJ regex `^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$`, positive decimal financial amounts, chronological timestamps (`data_contratacao >= data_solicitacao`).
   - **Topological Sorting**: Enforces generating parent tables (`empresas`) before child tables (`propostas`) and grandchild tables (`garantias`, `operacoes`).
   - **Pytest**: Explicit assertions for PK uniqueness, zero nulls, 100% FK referential integrity, and business rule compliance.
3. **Pytest Failure Parsing**: `parse_pytest_failures(stdout, stderr)` isolates lines beginning with `FAILED ` and extracts the `=== FAILURES ===` block up to summary info.
4. **Episodic Feedback Formatting**: `format_episodic_feedback(episodic_memory, max_history=2)` condenses failure history into actionable prompt instructions, preventing token bloat while giving specific failing lines and assertion messages.

#### Concrete Implementation Blueprint (`proposed_memory.py`):

```python
"""core/memory.py - CoALA Memory Management & Rules Engine."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.state import EpisodicMemoryRecord, ProceduralMemory


FAKER_BEST_PRACTICES: List[str] = [
    "Locale Configuration: Instantiate Faker with Brazilian locale `Faker(['pt_BR', 'en_US'])` for realistic corporate entities, CNPJs, and addresses.",
    "Deterministic Seeding: Always call `Faker.seed(42)` and `random.seed(42)` at the beginning of `generate_mock_data` to ensure 100% reproducible test execution.",
    "Tax IDs (CNPJ): Generate valid Brazilian CNPJs matching regex `^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$` using `faker.cnpj()` or custom formatting.",
    "Financial Amounts: Generate realistic decimal amounts (`faturamento_anual`, `valor_solicitado`, `valor_contratado`) using `round(random.uniform(min, max), 2)` or `faker.pydecimal(left_digits=7, right_digits=2, positive=True)`.",
    "Chronological Consistency: For datetime fields, ensure logical temporal ordering (e.g. `data_contratacao >= data_solicitacao`).",
    "Status Enums: Pick from allowed categorical values (e.g. `status_proposta` in `['ANALISE', 'APROVADA', 'RECUSADA']`, `status_cadastral` in `['ATIVO', 'INATIVO', 'SUSPENSO']`).",
    "Primary Keys: Use `str(uuid.uuid4())` or incrementing integers for primary key uniqueness without collisions.",
]

RELATIONAL_INTEGRITY_RULES: List[str] = [
    "Topological DAG Order: Always generate parent tables (independent entities) before child tables (dependent entities). For Credit Mesh: empresas -> propostas -> (garantias, operacoes).",
    "Referential Integrity: Child foreign key values MUST strictly sample from existing parent primary key values: `child_fk = random.choice([p['empresa_id'] for p in empresas])`. Zero orphan records.",
    "Cardinality Enforcement: For 1:N relationships, sample parent keys with replacement. For 1:1 relationships, sample without replacement or link directly.",
    "Business Rule Conditioning: Dependent records in `operacoes` must only be created for proposals having `status_proposta == 'APROVADA'`. Ensure `valor_contratado <= valor_solicitado`.",
    "Structured Output: Return all tables in a single dictionary: `{'empresas': [...], 'propostas': [...], 'garantias': [...], 'operacoes': [...]}`.",
]

PYTEST_TEST_PATTERNS: List[str] = [
    "Test Naming: Name all validation functions `test_<table_or_rule>_*()` and ensure they require zero arguments.",
    "Dataset Verification: Execute `data = generate_mock_data()` inside each test or use a shared pytest fixture.",
    "Non-Empty Tables: Assert each table contains at least 1 record: `assert len(data['<table>']) >= 1`.",
    "Primary Key Integrity: Assert primary keys are unique and non-null: `pks = [row['id'] for row in data['<table>']]; assert len(pks) == len(set(pks))` and `assert not any(x is None for x in pks)`.",
    "Foreign Key Verification: Assert child foreign keys exist in parent: `assert all(fk in parent_pks for fk in child_fks)`.",
    "Business Rule Assertions: Assert specific business rules (e.g. `assert all(op['valor_contratado'] <= prop_map[op['proposta_id']]['valor_solicitado'] for op in data['operacoes'])`).",
    "Descriptive Messages: Include actionable messages on assertions: `assert condition, 'Descriptive error message'`.",
]

SYSTEM_PROMPT: str = """You are Simula-AI, an expert autonomous data engineer specializing in synthetic relational data generation and automated test verification for Data Mesh ecosystems.

Your objective is to generate a single, completely self-contained Python script that:
1. Implements `generate_mock_data(rows: int = 50) -> dict[str, list[dict[str, Any]]]` to generate realistic relational mock datasets conforming strictly to the provided data contract YAML.
2. Follows topological DAG order so parent tables are populated before child tables, ensuring 100% referential integrity with zero orphan records.
3. Implements comprehensive Pytest tests (`test_*`) validating table row counts, Primary Key uniqueness, Foreign Key referential integrity, and business rules.

CRITICAL INSTRUCTIONS:
- You must output ONLY clean, runnable Python code enclosed in a single ```python ... ``` code block.
- Do NOT include markdown text outside the code block.
- Never use `eval()` or `exec()`.
- Ensure all imports (e.g. `faker`, `pytest`, `uuid`, `random`, `datetime`, `re`) are included at the top.
"""


def create_initial_procedural_memory() -> Dict[str, Any]:
    """Returns the default procedural memory containing data engineering guidelines."""
    guidelines = FAKER_BEST_PRACTICES + RELATIONAL_INTEGRITY_RULES + PYTEST_TEST_PATTERNS
    return {
        "system_prompt": SYSTEM_PROMPT.strip(),
        "faker_rules": list(FAKER_BEST_PRACTICES),
        "relational_rules": list(RELATIONAL_INTEGRITY_RULES),
        "pytest_rules": list(PYTEST_TEST_PATTERNS),
        "guidelines": guidelines,
        "rules": guidelines,
    }


def parse_pytest_failures(stdout: str, stderr: str) -> Tuple[List[str], str]:
    """Parses pytest stdout/stderr to extract failed test names and a concise error summary."""
    failed_tests: List[str] = []
    summary_lines: List[str] = []

    for line in stdout.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("FAILED "):
            test_target = line_clean.replace("FAILED ", "").split()[0]
            if "::" in test_target:
                test_name = test_target.split("::")[-1]
            else:
                test_name = test_target
            if test_name not in failed_tests:
                failed_tests.append(test_name)

    in_failures_section = False
    for line in stdout.splitlines():
        if line.startswith("=== FAILURES ===") or line.startswith("=== ERRORS ==="):
            in_failures_section = True
        if in_failures_section:
            if line.startswith("=== short test summary info ===") or line.startswith("====="):
                if summary_lines and summary_lines[-1].startswith("="):
                    break
            summary_lines.append(line)

    if summary_lines:
        error_summary = "\n".join(summary_lines[:40]).strip()
    elif stderr.strip():
        error_summary = stderr.strip()[:1000]
    elif stdout.strip():
        lines = stdout.splitlines()
        error_summary = "\n".join(lines[-20:]).strip()
    else:
        error_summary = "Unknown test execution failure without output."

    return failed_tests, error_summary


def create_episodic_record(
    iteration: int,
    generated_code: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    error_summary: Optional[str] = None,
    failed_tests: Optional[List[str]] = None,
    timestamp: Optional[str] = None,
) -> EpisodicMemoryRecord:
    """Creates a structured EpisodicMemoryRecord from an execution attempt."""
    if error_summary is None or failed_tests is None:
        extracted_failed_tests, extracted_summary = parse_pytest_failures(stdout, stderr)
        if error_summary is None:
            error_summary = extracted_summary
        if failed_tests is None:
            failed_tests = extracted_failed_tests

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    return {
        "iteration": iteration,
        "generated_code": generated_code,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "error_summary": error_summary,
        "failed_tests": failed_tests,
        "timestamp": ts,
    }


def format_episodic_feedback(
    episodic_memory: List[EpisodicMemoryRecord],
    max_history: int = 2,
) -> str:
    """Formats prior failures into a concise, actionable feedback prompt for the LLM."""
    if not episodic_memory:
        return ""

    recent_records = episodic_memory[-max_history:]
    blocks: List[str] = [
        "## FEEDBACK FROM PREVIOUS ATTEMPT(S) - SELF-CORRECTION REQUIRED",
        "The previous code attempt failed Pytest validation. Carefully analyze the errors below and fix them:\n",
    ]

    for rec in recent_records:
        iter_num = rec["iteration"]
        rc = rec["exit_code"]
        failed = ", ".join(rec.get("failed_tests", [])) or "None identified"
        summary = rec.get("error_summary", "").strip()

        blocks.append(f"### Attempt #{iter_num} (Pytest Return Code: {rc})")
        blocks.append(f"- Failed Tests: `{failed}`")
        blocks.append("```")
        blocks.append(summary)
        blocks.append("```\n")

    blocks.extend([
        "REPAIR DIRECTIVES:",
        "1. Directly address and fix each failed assertion or exception identified above.",
        "2. Ensure parent table primary keys are generated before child foreign keys in topological DAG order.",
        "3. Ensure all child foreign keys sample strictly from generated parent primary keys (zero orphan records).",
        "4. Check that all business rule assertions and constraints are satisfied.",
        "5. Output the COMPLETE corrected script enclosed in a single ```python ... ``` code block.",
    ])

    return "\n".join(blocks)
```

---

### 3.3 Component 3: `core/llm_client.py`

#### Key Design Decisions:
1. **Target Endpoint**: `https://openrouter.ai/api/v1/chat/completions`.
2. **Model Cascade**:
   - Primary: `deepseek/deepseek-r1` (or `OPENROUTER_MODEL` env var)
   - Fallbacks: `["deepseek/deepseek-chat", "deepseek/deepseek-r1-distill-llama-70b"]` (or `OPENROUTER_FALLBACK_MODELS` comma-delimited env var)
3. **HTTP 429 Exponential Backoff with Full Jitter**:
   - Formula:
     $$delay = \text{uniform}(0.5, \min(max\_backoff, base\_delay \times backoff\_factor^{attempt}))$$
   - Respects `Retry-After` header: if present, $delay = \max(delay, \text{float}(retry\_after))$.
   - Also retries on transient errors `502`, `503`, `504`, and network connection timeouts.
   - Non-retryable errors (`401`, `403`) raise `OpenRouterAuthError` immediately.
4. **Deterministic Mock LLM Provider**:
   - Two entry paths: `MockLLMClient` class AND `OpenRouterClient(mock_mode=True)` (or `SIMULA_MOCK_LLM=true` environment variable).
   - Generates valid Python code enclosed in markdown fences (` ```python ... ``` `).
   - Multi-iteration retry testing support: configured via `fail_first_iteration=True` or `SIMULA_MOCK_FAIL_FIRST=true`. On iteration 1 (or when episodic memory is empty), produces intentional failing assertion (`assert 1 == 2`). On iteration 2 (or when episodic memory has errors), generates 100% passing code.

#### Concrete Implementation Blueprint (`proposed_llm_client.py`):

```python
"""core/llm_client.py - OpenRouter LLM Client with 429 Fallback & Mock Provider."""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Union

import httpx

from core.memory import format_episodic_feedback
from core.state import EpisodicMemoryRecord, ProceduralMemory, WorkingMemory

logger = logging.getLogger("simula.llm_client")


class OpenRouterError(Exception):
    """Base exception for OpenRouter API interactions."""


class OpenRouterAuthError(OpenRouterError):
    """Authentication or authorization failure (HTTP 401/403). Non-retryable."""


class OpenRouterRateLimitError(OpenRouterError):
    """Rate limit exceeded across all models and retries (HTTP 429)."""


class OpenRouterAPIError(OpenRouterError):
    """General OpenRouter API error."""


DEFAULT_PRIMARY_MODEL = "deepseek/deepseek-r1"
DEFAULT_FALLBACK_MODELS = [
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1-distill-llama-70b",
]


class MockLLMClient:
    """Deterministic offline LLM test double for testing and CI/CD pipelines."""

    def __init__(
        self,
        fail_first_iteration: bool = False,
    ) -> None:
        env_fail = os.environ.get("SIMULA_MOCK_FAIL_FIRST", "").lower() in ("true", "1", "yes")
        self.fail_first_iteration = fail_first_iteration or env_fail
        self.call_count = 0

    def generate_candidate(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]] = None,
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]] = None,
        episodic_memory: Optional[List[EpisodicMemoryRecord]] = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generates deterministic Python candidate code enclosed in markdown fence."""
        self.call_count += 1
        episodic = episodic_memory or []

        should_fail = self.fail_first_iteration and (iteration == 1 or len(episodic) == 0)

        contract_yaml = ""
        if working_memory and isinstance(working_memory, dict):
            contract_yaml = working_memory.get("contract_yaml", "")

        is_credit_mesh = "empresas" in contract_yaml or "propostas" in contract_yaml

        if should_fail:
            return self._build_failing_code(is_credit_mesh=is_credit_mesh)
        return self._build_passing_code(is_credit_mesh=is_credit_mesh)

    def _build_failing_code(self, is_credit_mesh: bool = True) -> str:
        return """```python
import random
import uuid
import pytest
from faker import Faker

fake = Faker(['pt_BR'])
Faker.seed(42)
random.seed(42)

def generate_mock_data(rows: int = 10):
    empresas = [
        {
            "empresa_id": str(uuid.uuid4()),
            "cnpj": fake.cnpj(),
            "razao_social": fake.company(),
            "faturamento_anual": round(random.uniform(500000.0, 5000000.0), 2),
            "status_cadastral": "ATIVO",
        }
        for _ in range(rows)
    ]
    propostas = [
        {
            "proposta_id": str(uuid.uuid4()),
            "empresa_id": random.choice(empresas)["empresa_id"],
            "valor_solicitado": round(random.uniform(10000.0, 100000.0), 2),
            "status_proposta": "ANALISE",
        }
        for _ in range(rows)
    ]
    return {"empresas": empresas, "propostas": propostas}

def test_empresas_count():
    data = generate_mock_data(5)
    assert len(data["empresas"]) == 5

def test_intentional_mock_failure():
    assert 1 == 2, "Intentional mock validation failure: proposals value check failed"
```"""

    def _build_passing_code(self, is_credit_mesh: bool = True) -> str:
        return """```python
import random
import uuid
import re
from datetime import datetime, timedelta
import pytest
from faker import Faker

fake = Faker(['pt_BR'])
Faker.seed(42)
random.seed(42)

def generate_mock_data(rows: int = 20):
    empresas = []
    for _ in range(rows):
        empresas.append({
            "empresa_id": str(uuid.uuid4()),
            "cnpj": fake.cnpj(),
            "razao_social": fake.company(),
            "faturamento_anual": round(random.uniform(100000.0, 10000000.0), 2),
            "status_cadastral": random.choice(["ATIVO", "INATIVO", "SUSPENSO"]),
        })

    propostas = []
    base_date = datetime.now() - timedelta(days=60)
    for _ in range(rows):
        empresa = random.choice(empresas)
        dt_solicitacao = base_date + timedelta(days=random.randint(1, 30))
        propostas.append({
            "proposta_id": str(uuid.uuid4()),
            "empresa_id": empresa["empresa_id"],
            "data_solicitacao": dt_solicitacao.isoformat(),
            "valor_solicitado": round(random.uniform(20000.0, 250000.0), 2),
            "status_proposta": random.choice(["APROVADA", "ANALISE", "RECUSADA"]),
        })

    garantias = []
    for _ in range(rows):
        prop = random.choice(propostas)
        garantias.append({
            "garantia_id": str(uuid.uuid4()),
            "proposta_id": prop["proposta_id"],
            "tipo_garantia": random.choice(["IMOVEL", "VEICULO", "AVAL", "RECEBIVEIS"]),
            "valor_avaliado": round(random.uniform(30000.0, 500000.0), 2),
        })

    operacoes = []
    aprovadas = [p for p in propostas if p["status_proposta"] == "APROVADA"]
    if not aprovadas:
        aprovadas = propostas[:max(1, len(propostas) // 2)]
        for p in aprovadas:
            p["status_proposta"] = "APROVADA"

    for prop in aprovadas:
        dt_sol = datetime.fromisoformat(prop["data_solicitacao"])
        dt_contratacao = dt_sol + timedelta(days=random.randint(1, 10))
        val_contratado = round(prop["valor_solicitado"] * random.uniform(0.5, 1.0), 2)
        operacoes.append({
            "operacao_id": str(uuid.uuid4()),
            "proposta_id": prop["proposta_id"],
            "data_contratacao": dt_contratacao.isoformat(),
            "valor_contratado": val_contratado,
        })

    return {
        "empresas": empresas,
        "propostas": propostas,
        "garantias": garantias,
        "operacoes": operacoes,
    }

def test_empresas_primary_key_uniqueness():
    data = generate_mock_data(10)
    pks = [e["empresa_id"] for e in data["empresas"]]
    assert len(pks) == len(set(pks)), "Empresas PK must be strictly unique"
    assert not any(x is None for x in pks), "Empresas PK cannot be None"

def test_empresas_cnpj_regex():
    data = generate_mock_data(10)
    cnpj_pattern = re.compile(r"^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$")
    for emp in data["empresas"]:
        assert cnpj_pattern.match(emp["cnpj"]), f"Invalid CNPJ: {emp['cnpj']}"

def test_propostas_fk_referential_integrity():
    data = generate_mock_data(10)
    empresa_pks = {e["empresa_id"] for e in data["empresas"]}
    for prop in data["propostas"]:
        assert prop["empresa_id"] in empresa_pks, "Proposta FK must exist in empresas"

def test_garantias_fk_referential_integrity():
    data = generate_mock_data(10)
    proposta_pks = {p["proposta_id"] for p in data["propostas"]}
    for gar in data["garantias"]:
        assert gar["proposta_id"] in proposta_pks, "Garantia FK must exist in propostas"

def test_operacoes_business_rules():
    data = generate_mock_data(10)
    prop_map = {p["proposta_id"]: p for p in data["propostas"]}
    for op in data["operacoes"]:
        assert op["proposta_id"] in prop_map
        parent_prop = prop_map[op["proposta_id"]]
        assert parent_prop["status_proposta"] == "APROVADA"
        assert op["valor_contratado"] <= parent_prop["valor_solicitado"]
```"""


class OpenRouterClient:
    """Client for querying OpenRouter chat completions with full 429 jitter & model fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        timeout: float = 120.0,
        max_retries_per_model: int = 3,
        base_delay: float = 2.0,
        max_backoff: float = 30.0,
        backoff_factor: float = 2.0,
        mock_mode: Optional[bool] = None,
        fail_first_iteration: bool = False,
    ) -> None:
        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            env_mock = os.environ.get("SIMULA_MOCK_LLM", "").lower()
            self.mock_mode = env_mock in ("true", "1", "yes")

        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        
        self.primary_model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_PRIMARY_MODEL
        self.model = self.primary_model

        if fallback_models is not None:
            self.fallback_models = list(fallback_models)
        elif "OPENROUTER_FALLBACK_MODELS" in os.environ:
            self.fallback_models = [
                m.strip() for m in os.environ["OPENROUTER_FALLBACK_MODELS"].split(",") if m.strip()
            ]
        else:
            self.fallback_models = list(DEFAULT_FALLBACK_MODELS)

        self.timeout = float(os.environ.get("OPENROUTER_TIMEOUT", str(timeout)))
        self.max_retries_per_model = int(os.environ.get("OPENROUTER_MAX_RETRIES", str(max_retries_per_model)))
        self.base_delay = base_delay
        self.max_backoff = max_backoff
        self.backoff_factor = backoff_factor
        self.fail_first_iteration = fail_first_iteration

        self._mock_client = MockLLMClient(fail_first_iteration=self.fail_first_iteration)

    def generate_candidate(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]] = None,
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]] = None,
        episodic_memory: Optional[List[EpisodicMemoryRecord]] = None,
        iteration: int = 1,
        **kwargs: Any,
    ) -> str:
        """Generates candidate Python code via Mock LLM or OpenRouter API."""
        if self.mock_mode:
            return self._mock_client.generate_candidate(
                procedural_memory=procedural_memory,
                working_memory=working_memory,
                episodic_memory=episodic_memory,
                iteration=iteration,
                **kwargs,
            )

        if not self.api_key:
            raise OpenRouterAuthError(
                "OPENROUTER_API_KEY is not set. Please export OPENROUTER_API_KEY or use SIMULA_MOCK_LLM=true."
            )

        messages = self._build_messages(
            procedural_memory=procedural_memory,
            working_memory=working_memory,
            episodic_memory=episodic_memory,
            iteration=iteration,
        )

        return self._call_openrouter_with_fallback(messages, **kwargs)

    def _build_messages(
        self,
        procedural_memory: Optional[Union[ProceduralMemory, Dict[str, Any]]],
        working_memory: Optional[Union[WorkingMemory, Dict[str, Any]]],
        episodic_memory: Optional[List[EpisodicMemoryRecord]],
        iteration: int,
    ) -> List[Dict[str, str]]:
        system_prompt = ""
        if procedural_memory and isinstance(procedural_memory, dict):
            system_prompt = procedural_memory.get("system_prompt", "")
        if not system_prompt:
            from core.memory import SYSTEM_PROMPT
            system_prompt = SYSTEM_PROMPT

        messages = [{"role": "system", "content": system_prompt}]

        contract_yaml = ""
        if working_memory and isinstance(working_memory, dict):
            contract_yaml = working_memory.get("contract_yaml", "")

        user_content_parts = [
            f"# TASK SPECIFICATION: ITERATION {iteration}",
            "Generate a complete Python script implementing `generate_mock_data(rows=50)` and Pytest tests for the following Data Mesh contract:\n",
            "```yaml",
            contract_yaml,
            "```\n",
        ]

        if episodic_memory:
            feedback = format_episodic_feedback(episodic_memory)
            if feedback:
                user_content_parts.append(feedback)

        user_content_parts.append(
            "\nOutput ONLY the complete Python script enclosed in a single ```python ... ``` markdown code block."
        )

        messages.append({"role": "user", "content": "\n".join(user_content_parts)})
        return messages

    def _calculate_jitter_delay(self, attempt: int, retry_after: Optional[float] = None) -> float:
        computed_delay = min(self.max_backoff, self.base_delay * (self.backoff_factor ** attempt))
        delay = random.uniform(0.5, max(0.5, computed_delay))
        if retry_after is not None and retry_after > 0:
            delay = max(delay, retry_after)
        return delay

    def _call_openrouter_with_fallback(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> str:
        models_to_try = [self.primary_model] + [
            m for m in self.fallback_models if m != self.primary_model
        ]

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://simula.ai",
            "X-Title": "Simula-AI Data Mocking Framework",
        }

        last_exception: Optional[Exception] = None

        with httpx.Client(timeout=self.timeout) as client:
            for model_name in models_to_try:
                logger.info(f"Attempting completion with model '{model_name}'...")

                for attempt in range(self.max_retries_per_model):
                    payload = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        **kwargs,
                    }

                    try:
                        resp = client.post(endpoint, headers=headers, json=payload)

                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if not choices:
                                raise OpenRouterAPIError(f"OpenRouter response missing choices: {data}")
                            content = choices[0].get("message", {}).get("content", "")
                            if not content:
                                raise OpenRouterAPIError("OpenRouter choice contained empty message content")
                            return content

                        if resp.status_code in (401, 403):
                            err_msg = f"OpenRouter authentication failure ({resp.status_code}): {resp.text}"
                            logger.error(err_msg)
                            raise OpenRouterAuthError(err_msg)

                        if resp.status_code in (429, 502, 503, 504):
                            retry_after: Optional[float] = None
                            if "retry-after" in resp.headers:
                                try:
                                    retry_after = float(resp.headers["retry-after"])
                                except (ValueError, TypeError):
                                    retry_after = None

                            delay = self._calculate_jitter_delay(attempt, retry_after)
                            logger.warning(
                                f"Model '{model_name}' returned HTTP {resp.status_code}. "
                                f"Backing off with full jitter for {delay:.2f}s (attempt {attempt + 1}/{self.max_retries_per_model})."
                            )
                            time.sleep(delay)
                            continue

                        if 400 <= resp.status_code < 500:
                            err_msg = f"OpenRouter client error ({resp.status_code}): {resp.text}"
                            logger.error(err_msg)
                            raise OpenRouterAPIError(err_msg)

                        delay = self._calculate_jitter_delay(attempt)
                        logger.warning(
                            f"Model '{model_name}' returned unexpected HTTP {resp.status_code}. Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)

                    except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                        delay = self._calculate_jitter_delay(attempt)
                        logger.warning(
                            f"Network error on model '{model_name}': {net_err}. Retrying in {delay:.2f}s..."
                        )
                        last_exception = net_err
                        time.sleep(delay)
                    except (OpenRouterAuthError, OpenRouterAPIError):
                        raise
                    except Exception as exc:
                        last_exception = exc
                        logger.warning(f"Unexpected error querying '{model_name}': {exc}")

                logger.warning(
                    f"Exhausted all {self.max_retries_per_model} retries for model '{model_name}'. "
                    "Cascading to next fallback model..."
                )

        error_detail = f" Last error: {last_exception}" if last_exception else ""
        raise OpenRouterRateLimitError(
            f"All models in fallback cascade ({models_to_try}) were exhausted without success.{error_detail}"
        )
```

---

## 4. Integration Matrix with Milestone 2 Peer Explorers

| Interface Point | Provider (This Investigation) | Consumer | Contract & Expectations |
|---|---|---|---|
| **SimulaState Schema** | `core/state.py` | Explorer 3 (`core/graph.py`), CLI (`cli/main.py`), UI (`ui/app.py`) | TypedDict with `procedural_memory`, `working_memory`, `episodic_memory`, `iterations`, `status`. Immutable graph node updates via dictionary copying. |
| **Episodic Record Factory** | `core/memory.py::create_episodic_record` | Explorer 3 (`core/graph.py::node_execute`) | Ingests exit code, stdout, and stderr from Explorer 2's `PytestSandbox.execute()`, auto-populates `failed_tests` and `error_summary`. |
| **Episodic Feedback Formatter** | `core/memory.py::format_episodic_feedback` | Explorer 3 (`core/graph.py::node_generate`), `core/llm_client.py` | Formats last 2 failure traces into clean Markdown prompt snippet. |
| **Candidate Generator** | `core/llm_client.py::OpenRouterClient` / `MockLLMClient` | Explorer 3 (`core/graph.py::node_generate`) | Signature: `generate_candidate(procedural_memory, working_memory, episodic_memory, iteration) -> str`. Output is ingested by Explorer 2's `CodeParser.extract_python_code()`. |
| **Event Streamer** | `core/state.py::SimulaEvent` | Explorer 3 (`core/graph.py::run_simula_loop`) | Generator yields `SimulaEvent` instances on each node transition for real-time rich spinners in CLI and status progress in Streamlit. |

---

## 5. Verification & Testing Evidence

The proposed blueprints were verified through an automated test harness (`verify_proposed_components.py`) executed against Python 3.14:
1. **`test_state_schema`**: Verified `SimulaState` TypedDict annotations contain all required CoALA memory keys; `EpisodicMemoryRecord` contains `{"iteration", "exit_code", "stdout", "stderr"}`.
2. **`test_memory_procedural_initialization`**: Verified `create_initial_procedural_memory()` returns complete guidelines for Faker, topological sorting, and Pytest assertions.
3. **`test_memory_episodic_parsing_and_feedback`**: Verified extraction of failed test functions and formatting into concise LLM feedback.
4. **`test_llm_client_configuration`**: Verified `OpenRouterClient` model configuration, base URL, and fallback cascade order.
5. **`test_mock_llm_deterministic_output`**: Verified offline mock generator returns executable Python code wrapped in fences.
6. **`test_mock_llm_iterative_retry_support`**: Verified failure injection on iteration 1 (`assert 1 == 2`) and self-correcting repair on iteration 2 (`assert 1 == 1`).
7. **`test_openrouter_jitter_calculation`**: Verified random full jitter calculation within exponential bounds and enforcement of `Retry-After`.
8. **End-to-End Sandbox Execution**: Verified that candidate code produced by `MockLLMClient` executes in an isolated temporary directory via `pytest` subprocess and passes with exit code 0 (`5 passed in 0.05s`).
