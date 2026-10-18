"""core/memory.py - CoALA Memory Management & Rules Engine.

Implements:
1. Procedural Memory: Static domain knowledge, Faker generation rules,
   topological relational integrity guidelines, and Pytest validation patterns.
2. Episodic Memory: Dynamic failure capture, traceback parsing, and concise
   prompt formatting for iterative LLM self-correction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.state import EpisodicMemoryRecord

FAKER_BEST_PRACTICES: list[str] = [
    "Locale Configuration: Instantiate Faker with Brazilian locale `Faker(['pt_BR', 'en_US'])` for realistic corporate entities, CNPJs, and addresses.",
    "Deterministic Seeding: Always call `Faker.seed(42)` and `random.seed(42)` at the beginning of `generate_mock_data` to ensure 100% reproducible test execution.",
    "Tax IDs (CNPJ): Generate valid Brazilian CNPJs matching regex `^\\d{2}\\.\\d{3}\\.\\d{3}/\\d{4}-\\d{2}$` using `faker.cnpj()` or custom formatting.",
    "Financial Amounts: Generate realistic decimal amounts (`faturamento_anual`, `valor_solicitado`, `valor_contratado`) using `round(random.uniform(min, max), 2)` or `faker.pydecimal(left_digits=7, right_digits=2, positive=True)`.",
    "Chronological Consistency: For datetime fields, ensure logical temporal ordering (e.g. `data_contratacao >= data_solicitacao`).",
    "Status Enums: Pick from allowed categorical values (e.g. `status_proposta` in `['ANALISE', 'APROVADA', 'RECUSADA']`, `status_cadastral` in `['ATIVO', 'INATIVO', 'SUSPENSO']`).",
    "Primary Keys: Use `str(uuid.uuid4())` or incrementing integers for primary key uniqueness without collisions.",
]

RELATIONAL_INTEGRITY_RULES: list[str] = [
    "Topological DAG Order: Always generate parent tables (independent entities) before child tables (dependent entities). For Credit Mesh: empresas -> propostas -> (garantias, operacoes).",
    "Referential Integrity: Child foreign key values MUST strictly sample from existing parent primary key values: `child_fk = random.choice([p['empresa_id'] for p in empresas])`. Zero orphan records.",
    "Cardinality Enforcement: For 1:N relationships, sample parent keys with replacement. For 1:1 relationships, sample without replacement or link directly.",
    "Business Rule Conditioning: Dependent records in `operacoes` must only be created for proposals having `status_proposta == 'APROVADA'`. Ensure `valor_contratado <= valor_solicitado`.",
    "Structured Output: Return all tables in a single dictionary: `{'empresas': [...], 'propostas': [...], 'garantias': [...], 'operacoes': [...]}`.",
]

PYTEST_TEST_PATTERNS: list[str] = [
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


def create_initial_procedural_memory() -> dict[str, Any]:
    """Returns the default procedural memory containing data engineering guidelines.

    Satisfies CoALA procedural memory requirements for Faker best practices,
    topological relational generation rules, and Pytest assertion patterns.
    """
    guidelines = FAKER_BEST_PRACTICES + RELATIONAL_INTEGRITY_RULES + PYTEST_TEST_PATTERNS
    return {
        "system_prompt": SYSTEM_PROMPT.strip(),
        "faker_rules": list(FAKER_BEST_PRACTICES),
        "relational_rules": list(RELATIONAL_INTEGRITY_RULES),
        "pytest_rules": list(PYTEST_TEST_PATTERNS),
        "guidelines": guidelines,
        "rules": guidelines,
    }


def parse_pytest_failures(stdout: str, stderr: str) -> tuple[list[str], str]:
    """Parses pytest stdout/stderr to extract failed test names and a concise error summary.

    Args:
        stdout: Captured standard output from pytest subprocess.
        stderr: Captured standard error from pytest subprocess.

    Returns:
        A tuple of (failed_tests_list, failure_summary_string).
    """
    failed_tests: list[str] = []
    summary_lines: list[str] = []

    # 1. Extract test names from lines like "FAILED simula_temp_test.py::test_xxx - AssertionError..."
    # or "FAILED test_xxx"
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

    # 2. Extract the failures section from pytest output
    in_failures_section = False
    for line in stdout.splitlines():
        if line.startswith(("=== FAILURES ===", "=== ERRORS ===")):
            in_failures_section = True
        if in_failures_section:
            if (
                line.startswith(("=== short test summary info ===", "====="))
                and summary_lines
                and summary_lines[-1].startswith("=")
            ):
                break
            summary_lines.append(line)

    if summary_lines:
        error_summary = "\n".join(summary_lines[:40]).strip()
    elif stderr.strip():
        error_summary = stderr.strip()[:1000]
    elif stdout.strip():
        # Fallback to last 20 lines of stdout
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
    error_summary: str | None = None,
    failed_tests: list[str] | None = None,
    timestamp: str | None = None,
) -> EpisodicMemoryRecord:
    """Creates a structured EpisodicMemoryRecord from an execution attempt."""
    if error_summary is None or failed_tests is None:
        extracted_failed_tests, extracted_summary = parse_pytest_failures(stdout, stderr)
        if error_summary is None:
            error_summary = extracted_summary
        if failed_tests is None:
            failed_tests = extracted_failed_tests

    ts = timestamp or datetime.now(UTC).isoformat()
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
    episodic_memory: list[EpisodicMemoryRecord],
    max_history: int = 2,
) -> str:
    """Formats prior failures into a concise, actionable feedback prompt for the LLM.

    Focuses on the most recent failures to prevent context window bloat while
    giving specific assertion errors, tracebacks, and correction instructions.
    """
    if not episodic_memory:
        return ""

    recent_records = episodic_memory[-max_history:]
    blocks: list[str] = [
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
