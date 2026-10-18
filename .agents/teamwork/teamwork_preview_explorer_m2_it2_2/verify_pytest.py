import sys
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test_final_candidate import strip_think_tags as new_strip_think_tags
from test_final_candidate import extract_python_code as new_extract_python_code

import core.code_parser
core.code_parser.CodeParser.strip_think_tags = staticmethod(new_strip_think_tags)
core.code_parser.CodeParser.extract_python_code = classmethod(lambda cls, resp: new_extract_python_code(resp))

exit_code = pytest.main(["-v", "tests/unit/test_coala_loop.py"])
print(f"Pytest unit exit code: {exit_code}")
assert exit_code == 0, f"Expected pytest exit code 0, got {exit_code}"
print("All test_coala_loop unit tests PASSED!")
