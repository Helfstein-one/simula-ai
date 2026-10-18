import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import candidate functions
from test_final_candidate import strip_think_tags as new_strip_think_tags
from test_final_candidate import extract_python_code as new_extract_python_code

# Monkeypatch core.code_parser.CodeParser
import core.code_parser
core.code_parser.CodeParser.strip_think_tags = staticmethod(new_strip_think_tags)
core.code_parser.CodeParser.extract_python_code = classmethod(lambda cls, resp: new_extract_python_code(resp))

# Run the 22-test stress harness
import importlib.util
spec = importlib.util.spec_from_file_location(
    "stress_test_m2",
    PROJECT_ROOT / ".agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py"
)
stress_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stress_mod)

summary = stress_mod.run_all_stress_tests()
print("\n" + "=" * 80)
print(f"VERIFICATION SUMMARY: {summary['passed']}/{summary['total']} PASSED | DEFECTS: {summary['defects_or_findings']}")
print("=" * 80)
assert summary['passed'] == 22, f"Expected 22 passed, got {summary['passed']}"
print("ALL 22 ADVERSARIAL STRESS TESTS PASSED 100%!")
