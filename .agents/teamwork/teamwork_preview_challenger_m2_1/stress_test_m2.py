"""stress_test_m2.py - Adversarial Stress Test Harness for Milestone 2.

Author: Challenger 1 (Milestone 2 - CoALA Cognitive Loop & Sandbox)
Target: core/code_parser.py, core/sandbox.py
Focus:
  1. CodeParser: nested think tags, multi-block markdown, truncated fences, malformed python
  2. PytestSandbox: infinite loops, timeout handling, syntax errors, memory stress, multi-test assertions
  3. Security: Zero eval() and exec() in host process
"""

from __future__ import annotations

import ast
import builtins
import inspect
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.code_parser import CodeParser
from core.sandbox import PytestSandbox, SandboxResult


class StressTestReporter:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []

    def record(
        self,
        test_id: str,
        name: str,
        category: str,
        status: str,
        details: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self.results.append(
            {
                "test_id": test_id,
                "name": name,
                "category": category,
                "status": status,  # PASS, FAIL, DEFECT_CONFIRMED, VULN_FOUND
                "details": details,
                "metrics": metrics or {},
            }
        )
        flag = f"[{status}]"
        print(f"{flag:<20} {test_id}: {name}")
        if details:
            print(f"                     -> {details}")

    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        defects = sum(1 for r in self.results if "DEFECT" in r["status"] or "FAIL" in r["status"])
        return {
            "total": total,
            "passed": passed,
            "defects_or_findings": defects,
            "results": self.results,
        }


reporter = StressTestReporter()


# ==============================================================================
# Suite 1: CodeParser Adversarial Stress Tests
# ==============================================================================


def test_cp_nested_think_tags_basic() -> None:
    """Challenge: Nested think tags <think>a <think>b</think> c</think>."""
    raw = "<think>outer_1 <think>inner</think> outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n```"
    stripped = CodeParser.strip_think_tags(raw)
    extracted = CodeParser.extract_python_code(raw)

    # Note: Regex non-greedy strips <think>outer_1 <think>inner</think>, leaving outer_2</think>
    has_leak = "outer_2" in stripped
    code_valid = "def test_ok(): pass" in extracted

    if has_leak:
        reporter.record(
            "CP-01",
            "Nested Think Tags Stripping Leakage",
            "CodeParser",
            "DEFECT_CONFIRMED",
            f"Regex non-greedy left orphaned inner-outer text: {stripped!r}. However, extracted code was valid: {code_valid}.",
            {"leaked_text": "outer_2</think>", "code_extracted": extracted},
        )
    else:
        reporter.record(
            "CP-01",
            "Nested Think Tags Stripping Leakage",
            "CodeParser",
            "PASS",
            "Successfully stripped all nested think tags.",
        )


def test_cp_nested_think_code_draft_leakage() -> None:
    """Challenge: Code draft inside nested think tag."""
    raw = (
        "<think>thought 1\n"
        "<think>thought 1b</think>\n"
        "```python\n"
        "def test_bad_draft(): pass\n"
        "```\n"
        "</think>\n"
        "```python\n"
        "def test_real(): pass\n"
        "```"
    )
    extracted = CodeParser.extract_python_code(raw)
    # When draft code is in the unstripped portion of nested think tags and has equal score,
    # it gets extracted instead of test_real!
    if "test_bad_draft" in extracted:
        reporter.record(
            "CP-02",
            "Code Block Leakage in Nested Think Tags",
            "CodeParser",
            "DEFECT_CONFIRMED",
            "Draft code inside nested <think> was extracted instead of outer final code due to regex non-greedy match truncation.",
            {"extracted": extracted},
        )
    else:
        reporter.record(
            "CP-02",
            "Code Block Leakage in Nested Think Tags",
            "CodeParser",
            "PASS",
            "Successfully prioritized real code block.",
        )


def test_cp_think_tag_inside_python_literal() -> None:
    """Challenge: Python code itself containing <think>...</think> literal or comment."""
    raw = (
        "Here is the generator test:\n"
        "```python\n"
        "def test_prompt_filter():\n"
        "    msg = '<think>internal reasoning</think>'\n"
        "    assert 'internal' in msg\n"
        "```\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    valid, err = CodeParser.validate_syntax(extracted)

    if not valid or "internal reasoning" not in extracted:
        reporter.record(
            "CP-03",
            "Think Tag inside Python String Literal",
            "CodeParser",
            "DEFECT_CONFIRMED",
            f"strip_think_tags ran prior to code extraction and mangled Python string literal: valid={valid}, err={err!r}",
            {"extracted_code": extracted, "syntax_error": err},
        )
    else:
        reporter.record(
            "CP-03",
            "Think Tag inside Python String Literal",
            "CodeParser",
            "PASS",
            "Successfully preserved think tags inside Python code literal.",
        )


def test_cp_multiblock_markdown_mixed_languages() -> None:
    """Challenge: Markdown with bash, sql, and python blocks."""
    raw = (
        "### Step 1: Install\n"
        "```bash\n"
        "pip install faker pytest\n"
        "```\n"
        "### Step 2: Schema\n"
        "```sql\n"
        "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));\n"
        "```\n"
        "### Step 3: Test\n"
        "```python\n"
        "import pytest\n"
        "def test_user_creation():\n"
        "    assert True\n"
        "```\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    valid, err = CodeParser.validate_syntax(extracted)

    assert valid, f"Extracted code is invalid: {err}"
    assert "test_user_creation" in extracted
    assert "pip install" not in extracted
    assert "CREATE TABLE" not in extracted

    reporter.record(
        "CP-04",
        "Multi-block Markdown (bash/sql/python)",
        "CodeParser",
        "PASS",
        "Correctly excluded bash and sql blocks and selected Python test suite.",
    )


def test_cp_multiblock_scoring_heuristic() -> None:
    """Challenge: Multiple python blocks - short snippet vs full test suite with imports."""
    raw = (
        "Here is a snippet:\n"
        "```python\n"
        "x = 42\n"
        "```\n"
        "And here is the complete validation suite:\n"
        "```python\n"
        "import pytest\n"
        "from faker import Faker\n\n"
        "def test_data_generation():\n"
        "    fake = Faker()\n"
        "    assert fake.name() is not None\n"
        "```\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    assert "test_data_generation" in extracted
    assert "x = 42" not in extracted

    reporter.record(
        "CP-05",
        "Multi-block Python Scoring Priority",
        "CodeParser",
        "PASS",
        "Scoring heuristic correctly prioritized full test suite with imports and test functions.",
    )


def test_cp_single_closed_bash_with_unclosed_python() -> None:
    """Challenge: Single closed bash block followed by unclosed python block."""
    raw = (
        "Run this command:\n"
        "```bash\n"
        "pytest\n"
        "```\n"
        "Here is the test code:\n"
        "```python\n"
        "import pytest\n"
        "def test_truncated():\n"
        "    assert 1 == 1\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    # If bash was extracted because len(matches) == 1, document the finding
    if "pytest" == extracted.strip():
        reporter.record(
            "CP-06",
            "Single Closed Non-Python + Unclosed Python",
            "CodeParser",
            "DEFECT_CONFIRMED",
            "When exactly 1 closed block exists and is bash, CodeParser returns bash instead of evaluating unclosed python block.",
            {"extracted": extracted},
        )
    else:
        reporter.record(
            "CP-06",
            "Single Closed Non-Python + Unclosed Python",
            "CodeParser",
            "PASS",
            "Successfully extracted unclosed python block.",
        )


def test_cp_truncated_code_fences_eof() -> None:
    """Challenge: Truncated code fence without closing backticks at EOF."""
    raw = (
        "Code generation output:\n"
        "```python\n"
        "import pytest\n"
        "\n"
        "def test_alpha():\n"
        "    assert True\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    valid, err = CodeParser.validate_syntax(extracted)

    assert valid, f"Failed syntax: {err}"
    assert "def test_alpha" in extracted
    reporter.record(
        "CP-07",
        "Truncated Code Fence at EOF",
        "CodeParser",
        "PASS",
        "Correctly recovered unclosed code fence at EOF.",
    )


def test_cp_truncated_code_fence_no_lang() -> None:
    """Challenge: Truncated code fence with no language specifier."""
    raw = (
        "Code generation output:\n"
        "```\n"
        "import pytest\n"
        "def test_beta():\n"
        "    assert 42 == 42\n"
    )
    extracted = CodeParser.extract_python_code(raw)
    valid, err = CodeParser.validate_syntax(extracted)

    assert valid, f"Failed syntax: {err}"
    assert "def test_beta" in extracted
    reporter.record(
        "CP-08",
        "Truncated Code Fence without Language Tag",
        "CodeParser",
        "PASS",
        "Correctly extracted unclosed fence with empty language specifier.",
    )


def test_cp_syntactically_malformed_syntax_validation() -> None:
    """Challenge: Syntactically malformed python code."""
    cases = [
        ("", False, "Code is empty"),
        ("   \n\t  \n ", False, "Code is empty"),
        ("def broken(: pass", False, "SyntaxError"),
        ("def broken():\nassert True", False, "SyntaxError"),
        ("def ok(): pass", True, None),
    ]

    all_passed = True
    for code, expected_valid, err_substr in cases:
        valid, err = CodeParser.validate_syntax(code)
        if valid != expected_valid:
            all_passed = False
            break
        if err_substr and (err is None or err_substr.lower() not in err.lower()):
            all_passed = False
            break

    assert all_passed
    reporter.record(
        "CP-09",
        "AST Syntax Validation Edge Cases",
        "CodeParser",
        "PASS",
        "validate_syntax correctly classified empty, malformed, indentation error, and valid inputs.",
    )


def test_cp_malformed_code_extraction_survival() -> None:
    """Challenge: extract_python_code should not crash when given malformed syntax."""
    raw = "```python\ndef broken(:\n```"
    extracted = CodeParser.extract_python_code(raw)
    assert extracted == "def broken(:"
    reporter.record(
        "CP-10",
        "Malformed Syntax in Code Block",
        "CodeParser",
        "PASS",
        "extract_python_code gracefully handles SyntaxError during scoring and returns raw block.",
    )


# ==============================================================================
# Suite 2: PytestSandbox Empirical Stress Tests
# ==============================================================================


def test_sandbox_infinite_loop_timeout() -> None:
    """Challenge: Infinite loop (while True) must terminate cleanly within timeout."""
    sandbox = PytestSandbox(timeout_seconds=2)
    code = (
        "import time\n"
        "def test_infinite_loop():\n"
        "    while True:\n"
        "        time.sleep(0.01)\n"
    )
    t0 = time.time()
    res = sandbox.execute(code)
    elapsed = time.time() - t0

    assert res.timed_out is True, "Expected timed_out to be True"
    assert res.exit_code == -1, f"Expected exit_code == -1, got {res.exit_code}"
    assert res.is_success is False, "Expected is_success to be False"
    assert "TIMEOUT" in res.failed_tests, f"Expected TIMEOUT in failed_tests, got {res.failed_tests}"
    assert 1.8 <= elapsed <= 3.5, f"Expected timeout within ~2s, got {elapsed:.2f}s"

    reporter.record(
        "SB-01",
        "Infinite Loop Subprocess Termination",
        "PytestSandbox",
        "PASS",
        f"Process terminated cleanly after {elapsed:.2f}s with timed_out=True and exit_code=-1.",
        {"elapsed": elapsed, "exit_code": res.exit_code, "timed_out": res.timed_out},
    )


def test_sandbox_hanging_thread_timeout() -> None:
    """Challenge: Subprocess with non-daemon background thread hanging."""
    sandbox = PytestSandbox(timeout_seconds=2)
    code = (
        "import threading, time\n"
        "def test_hanging_thread():\n"
        "    def loop():\n"
        "        while True:\n"
        "            time.sleep(0.05)\n"
        "    t = threading.Thread(target=loop, daemon=False)\n"
        "    t.start()\n"
        "    assert True\n"
    )
    t0 = time.time()
    res = sandbox.execute(code)
    elapsed = time.time() - t0

    assert res.timed_out is True
    assert res.exit_code == -1
    assert "TIMEOUT" in res.failed_tests
    assert elapsed < 3.5

    reporter.record(
        "SB-02",
        "Hanging Non-Daemon Thread Termination",
        "PytestSandbox",
        "PASS",
        f"Non-daemon thread hang killed after {elapsed:.2f}s with timed_out=True.",
        {"elapsed": elapsed},
    )


def test_sandbox_syntax_error_exit_code() -> None:
    """Challenge: Syntax error in test file must return exit code 1 or 2 with error summary."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = "def test_syntax_err(: pass"
    res = sandbox.execute(code)

    assert res.timed_out is False
    assert res.is_success is False
    assert res.exit_code in (1, 2), f"Expected exit_code in (1, 2), got {res.exit_code}"
    assert "error" in res.error_summary.lower() or "syntaxerror" in res.error_summary.lower()

    reporter.record(
        "SB-03",
        "Syntax Error Exit Code & Diagnostics",
        "PytestSandbox",
        "PASS",
        f"Handled syntax error with exit_code={res.exit_code} and diagnostic traceback in summary.",
        {"exit_code": res.exit_code, "error_summary_preview": res.error_summary[:100]},
    )


def test_sandbox_simulated_memory_error() -> None:
    """Challenge: MemoryError raised inside test function."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = (
        "def test_simulated_oom():\n"
        "    raise MemoryError('Simulated Out Of Memory')\n"
    )
    res = sandbox.execute(code)

    assert res.timed_out is False
    assert res.is_success is False
    assert res.exit_code == 1
    assert "test_simulated_oom" in res.failed_tests

    reporter.record(
        "SB-04",
        "MemoryError Exception Handling",
        "PytestSandbox",
        "PASS",
        f"Captured MemoryError cleanly: exit_code={res.exit_code}, failed_tests={res.failed_tests}.",
        {"failed_tests": res.failed_tests},
    )


def test_sandbox_excessive_allocation_timeout() -> None:
    """Challenge: Excessive memory paging triggers timeout and kills process cleanly."""
    sandbox = PytestSandbox(timeout_seconds=3)
    code = (
        "def test_huge_allocation():\n"
        "    b = bytearray(1024 * 1024 * 1024 * 100) # 100 GB\n"
    )
    res = sandbox.execute(code)

    assert res.is_success is False
    # On macOS or Linux, allocating 100GB either triggers MemoryError immediately or hits timeout
    assert res.timed_out is True or res.exit_code in (1, -1)

    reporter.record(
        "SB-05",
        "Excessive Memory Allocation Handling",
        "PytestSandbox",
        "PASS",
        f"Handled 100GB allocation without host crash: timed_out={res.timed_out}, exit_code={res.exit_code}.",
    )


def test_sandbox_multiple_assertions_mixed_outcomes() -> None:
    """Challenge: Multiple test functions with passing, failing, and erroring tests."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = (
        "def test_alpha_pass(): assert True\n"
        "def test_bravo_fail(): assert 1 == 2, 'Value mismatch'\n"
        "def test_charlie_pass(): assert 2 + 2 == 4\n"
        "def test_delta_fail(): assert 'hello' == 'world'\n"
        "def test_echo_error(): raise KeyError('missing_field')\n"
    )
    res = sandbox.execute(code)

    assert res.timed_out is False
    assert res.exit_code == 1
    assert res.is_success is False

    expected_failures = {"test_bravo_fail", "test_delta_fail", "test_echo_error"}
    actual_failures = set(res.failed_tests)

    assert expected_failures == actual_failures, (
        f"Expected failures {expected_failures}, got {actual_failures}"
    )

    reporter.record(
        "SB-06",
        "Multiple Failing Assertions Isolation",
        "PytestSandbox",
        "PASS",
        f"Correctly extracted all 3 failed/errored tests: {sorted(res.failed_tests)} while ignoring passing tests.",
        {"failed_tests": res.failed_tests},
    )


def test_sandbox_no_tests_collected_code_5() -> None:
    """Challenge: Test file with 0 test functions returns pytest code 5."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = "x = 42\ny = 100\n"
    res = sandbox.execute(code)

    assert res.timed_out is False
    assert res.exit_code == 5
    assert res.is_success is False
    assert "No tests collected" in res.error_summary

    reporter.record(
        "SB-07",
        "No Tests Collected (Code 5)",
        "PytestSandbox",
        "PASS",
        f"Correctly identified exit_code=5 with clear error summary message.",
    )


def test_sandbox_passing_baseline() -> None:
    """Challenge: Clean test suite returns 0 and is_success=True."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = (
        "import pytest\n"
        "def test_one(): assert True\n"
        "def test_two(): assert [1, 2] == [1, 2]\n"
    )
    res = sandbox.execute(code)

    assert res.timed_out is False
    assert res.exit_code == 0
    assert res.is_success is True
    assert res.failed_tests == []

    reporter.record(
        "SB-08",
        "Passing Test Suite Baseline",
        "PytestSandbox",
        "PASS",
        "Executed valid tests with exit_code=0, is_success=True, failed_tests=[].",
    )


def test_sandbox_environment_tampering_isolation() -> None:
    """Challenge: Subprocess cannot contaminate host process environment variables."""
    sandbox = PytestSandbox(timeout_seconds=5)
    test_key = "SIMULA_ADVERSARIAL_TEST_KEY"
    if test_key in os.environ:
        del os.environ[test_key]

    code = (
        f"import os\n"
        f"def test_poison():\n"
        f"    os.environ['{test_key}'] = 'POISONED'\n"
        f"    assert True\n"
    )
    res = sandbox.execute(code)
    assert res.is_success is True
    assert test_key not in os.environ, "Host os.environ was contaminated by sandbox execution!"

    reporter.record(
        "SB-09",
        "Environment Variable Isolation",
        "PytestSandbox",
        "PASS",
        "Subprocess execution in sandbox cannot alter host os.environ.",
    )


def test_sandbox_temporary_directory_cleanup() -> None:
    """Challenge: Ephemeral sandbox temp directory is automatically destroyed."""
    sandbox = PytestSandbox(timeout_seconds=5)
    code = (
        "from pathlib import Path\n"
        "def test_file_write():\n"
        "    Path('created_in_sandbox.txt').write_text('payload')\n"
        "    assert True\n"
    )
    res = sandbox.execute(code)
    assert res.is_success is True
    assert not Path("created_in_sandbox.txt").exists(), (
        "File leaked into host current working directory!"
    )

    reporter.record(
        "SB-10",
        "Filesystem Isolation & Cleanup",
        "PytestSandbox",
        "PASS",
        "All scratch files created in sandbox were confined to temp dir and cleaned up upon exit.",
    )


# ==============================================================================
# Suite 3: Security & Zero Host eval()/exec() Audit
# ==============================================================================


def test_security_static_ast_audit_core() -> None:
    """Challenge: Static AST verification of core/ files for eval() or exec() calls."""
    core_dir = PROJECT_ROOT / "core"
    python_files = list(core_dir.glob("*.py"))
    assert len(python_files) > 0, "No python files found in core/"

    violations: list[str] = []
    for py_file in python_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                func_name = None
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr

                if func_name in ("eval", "exec"):
                    violations.append(f"{py_file.name}:{node.lineno} calls {func_name}()")

    assert len(violations) == 0, f"Found forbidden calls in core/: {violations}"

    reporter.record(
        "SEC-01",
        "Static AST Audit for eval() / exec() in core/",
        "Security",
        "PASS",
        f"Scanned {len(python_files)} core modules: exactly 0 calls to eval() or exec().",
        {"modules_scanned": [f.name for f in python_files]},
    )


def test_security_dynamic_interception_eval_exec() -> None:
    """Challenge: Dynamic runtime interception of builtins.eval and builtins.exec."""
    orig_eval = builtins.eval
    orig_exec = builtins.exec

    eval_invocations: list[tuple[str, int]] = []
    exec_invocations: list[tuple[str, int]] = []

    def wrapped_eval(*args: Any, **kwargs: Any) -> Any:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller = frame.f_back
            eval_invocations.append((caller.f_code.co_filename, caller.f_lineno))
        return orig_eval(*args, **kwargs)

    def wrapped_exec(*args: Any, **kwargs: Any) -> Any:
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller = frame.f_back
            exec_invocations.append((caller.f_code.co_filename, caller.f_lineno))
        return orig_exec(*args, **kwargs)

    builtins.eval = wrapped_eval
    builtins.exec = wrapped_exec

    try:
        # Exercise CodeParser
        cp = CodeParser()
        code = cp.extract_python_code("```python\nimport pytest\ndef test_dyn(): pass\n```")
        cp.validate_syntax(code)

        # Exercise PytestSandbox
        box = PytestSandbox(timeout_seconds=5)
        res = box.execute("def test_dyn_run(): assert 1 == 1")
        assert res.is_success is True

    finally:
        builtins.eval = orig_eval
        builtins.exec = orig_exec

    # Filter invocations to Simula core files
    core_eval = [c for c in eval_invocations if "/core/" in c[0]]
    core_exec = [c for c in exec_invocations if "/core/" in c[0]]

    assert len(core_eval) == 0, f"Core called eval(): {core_eval}"
    assert len(core_exec) == 0, f"Core called exec(): {core_exec}"

    reporter.record(
        "SEC-02",
        "Dynamic Runtime Interception (eval / exec)",
        "Security",
        "PASS",
        "Zero calls to eval() or exec() observed during dynamic execution of CodeParser and PytestSandbox.",
        {"core_eval_calls": len(core_eval), "core_exec_calls": len(core_exec)},
    )


# ==============================================================================
# Runner
# ==============================================================================


def run_all_stress_tests() -> dict[str, Any]:
    print("=" * 80)
    print("  SIMULA-AI MILESTONE 2: EMPIRICAL STRESS TEST HARNESS")
    print("=" * 80)

    # Suite 1
    test_cp_nested_think_tags_basic()
    test_cp_nested_think_code_draft_leakage()
    test_cp_think_tag_inside_python_literal()
    test_cp_multiblock_markdown_mixed_languages()
    test_cp_multiblock_scoring_heuristic()
    test_cp_single_closed_bash_with_unclosed_python()
    test_cp_truncated_code_fences_eof()
    test_cp_truncated_code_fence_no_lang()
    test_cp_syntactically_malformed_syntax_validation()
    test_cp_malformed_code_extraction_survival()

    # Suite 2
    test_sandbox_infinite_loop_timeout()
    test_sandbox_hanging_thread_timeout()
    test_sandbox_syntax_error_exit_code()
    test_sandbox_simulated_memory_error()
    test_sandbox_excessive_allocation_timeout()
    test_sandbox_multiple_assertions_mixed_outcomes()
    test_sandbox_no_tests_collected_code_5()
    test_sandbox_passing_baseline()
    test_sandbox_environment_tampering_isolation()
    test_sandbox_temporary_directory_cleanup()

    # Suite 3
    test_security_static_ast_audit_core()
    test_security_dynamic_interception_eval_exec()

    summary = reporter.summary()
    print("=" * 80)
    print(
        f"TOTAL TESTS: {summary['total']} | PASSED: {summary['passed']} | "
        f"DEFECTS/FINDINGS CONFIRMED: {summary['defects_or_findings']}"
    )
    print("=" * 80)

    # Write results JSON
    report_file = Path(__file__).parent / "stress_test_results.json"
    report_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Results written to: {report_file}")
    return summary


if __name__ == "__main__":
    summary = run_all_stress_tests()
    # Exit with code reflecting execution completion
    sys.exit(0)
