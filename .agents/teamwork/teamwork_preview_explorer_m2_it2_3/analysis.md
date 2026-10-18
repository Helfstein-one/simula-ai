# Analysis: Candidate Filtering Defect CP-06 in `core/code_parser.py`

## 1. Problem Statement & Scope

During Milestone 2 adversarial stress testing by Challenger 1, defect **CP-06** was uncovered in `core/code_parser.py`:
- In `stress_test_m2.py`, test case `test_cp_single_closed_bash_with_unclosed_python()` resulted in `DEFECT_CONFIRMED`.
- When an LLM generates a response containing a single closed non-Python block (e.g. ````bash\npytest\n````) followed by an unclosed Python block (e.g. ````python\nimport pytest\ndef test_truncated():\n    assert 1 == 1`), `CodeParser.extract_python_code` extracted the bash command `"pytest"` instead of the Python test block.

### Investigation Focus
1. Root cause analysis of candidate filtering condition at `core/code_parser.py:89`.
2. Root cause analysis of why the unclosed Python code block fallback fails when closed non-Python blocks precede it.
3. Formulate the exact fix strategy and patch to resolve CP-06 without regressing any existing tests.

---

## 2. Root Cause Analysis

### 2.1 The Guard Condition Defect (`core/code_parser.py:89`)
In `core/code_parser.py`:
```python
88: # Exclude explicit non-python blocks if alternatives exist
89: if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:
90:     continue
91: candidates.append(body_clean)
```

**Flaw Mechanism**:
- `CODE_BLOCK_PATTERN.findall(cleaned_text)` matches only closed blocks (` ```...``` `).
- When a response contains exactly 1 closed block (e.g., `bash`) and 1 unclosed block (e.g., `python`), `matches` contains only 1 item: `[('bash', 'pytest\n')]`.
- `len(matches)` evaluates to `1`.
- The condition `len(matches) > 1` evaluates to `False`.
- Consequently, `if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:` does **not** trigger `continue`.
- The non-Python block (`'pytest'`) is erroneously appended to `candidates`.
- Because `candidates` is now non-empty (`len(candidates) == 1`), the fallback `if not candidates:` (line 94) is bypassed completely!
- `_score_candidate('pytest')` returns `6`, and `"pytest"` is returned as the extracted Python code.

### 2.2 The Greedy Fallback Swallowing Defect (`core/code_parser.py:94-100`)
Merely removing `and len(matches) > 1` (changing line 89 to `if lang_clean in NON_PYTHON_LANGUAGES: continue`) solves candidate filtering for closed blocks, but exposes a secondary defect in the unclosed fallback:
```python
94: if not candidates:
95:     unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(cleaned_text)
96:     for lang, body in unclosed_matches:
97:         lang_clean = lang.strip().lower()
98:         body_clean = body.strip()
99:         if body_clean and lang_clean not in NON_PYTHON_LANGUAGES:
100:            candidates.append(body_clean)
```

Where `UNCLOSED_CODE_BLOCK_PATTERN` is defined at line 27:
```python
27: UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
28:     r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*)$",
29:     flags=re.DOTALL,
30: )
```

**Empirical Finding**:
When `cleaned_text` contains:
```markdown
Run this command:
```bash
pytest
```
Here is the test code:
```python
import pytest
def test_truncated():
    assert 1 == 1
```
Because `UNCLOSED_CODE_BLOCK_PATTERN` uses `(.*)$` with `re.DOTALL`, regex evaluation begins at the **first** triple backtick in `cleaned_text` (` ```bash `) and greedily captures everything to EOF!
- `lang` is captured as `"bash"`.
- `body` is captured as `"pytest\n```\nHere is the test code:\n```python\nimport pytest\ndef test_truncated():\n    assert 1 == 1\n"`.
- Because `lang_clean` is `"bash"`, line 99 (`lang_clean not in NON_PYTHON_LANGUAGES`) evaluates to `False`.
- The unclosed match is discarded!
- `candidates` remains empty!
- Execution then falls through to raw line scanning (`first_code_idx`), which is brittle (fails if unclosed block begins with comments, docstrings, or non-keyword expressions).

---

## 3. Recommended Fix Strategy

### 3.1 Unconditional Exclusion of Non-Python Languages
Change line 89 to unconditionally reject any block whose language tag is in `NON_PYTHON_LANGUAGES`:
```python
# Exclude explicit non-python blocks unconditionally
if lang_clean in NON_PYTHON_LANGUAGES:
    continue
```
Explicit non-Python blocks (`bash`, `sh`, `sql`, `yaml`, `json`, etc.) should **never** be admitted as Python candidates.

### 3.2 Pre-strip Closed Blocks Before Unclosed Fallback
Before running `UNCLOSED_CODE_BLOCK_PATTERN.findall`, remove all closed blocks using `CODE_BLOCK_PATTERN.sub("", cleaned_text)`:
```python
# Fallback to unclosed code block if truncated
if not candidates:
    text_for_unclosed = CODE_BLOCK_PATTERN.sub("", cleaned_text)
    unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(text_for_unclosed)
    for lang, body in unclosed_matches:
        lang_clean = lang.strip().lower()
        body_clean = body.strip()
        if body_clean and lang_clean not in NON_PYTHON_LANGUAGES:
            candidates.append(body_clean)
```

**Why This Works**:
1. All closed blocks (which were already processed and rejected or non-python) are erased.
2. In `text_for_unclosed`, the first remaining opening fence is guaranteed to be the genuine unclosed block (e.g. ````python\n...````).
3. `UNCLOSED_CODE_BLOCK_PATTERN` matches `lang = "python"` and cleanly captures `body` without preceding bash or markdown noise.
4. `lang_clean not in NON_PYTHON_LANGUAGES` evaluates to `True`.
5. The unclosed Python block is appended to `candidates` and scored correctly.

---

## 4. Verification Evidence

### 4.1 Verification on CP-06
Input:
```markdown
Run this command:
```bash
pytest
```
Here is the test code:
```python
import pytest
def test_truncated():
    assert 1 == 1
```

- **Before fix**: Extracted `'pytest'` -> `DEFECT_CONFIRMED` in CP-06.
- **After fix**: Extracted `'import pytest\ndef test_truncated():\n    assert 1 == 1'` -> `PASS` in CP-06.

### 4.2 Multi-Block & Leading Comment Tests
Tested against:
1. Multiple closed non-python blocks (`bash` + `sql`) followed by unclosed `python`: Extracted `import pytest\ndef test_ok(): pass`.
2. Unclosed python block starting with comments (`# Test suite\nimport pytest...`): Extracted full block including comments (does not rely on raw line fallback).
3. Single closed non-python block only (no python anywhere): Cleanly falls back to `cleaned_text.strip()`.
4. All existing tests in `stress_test_m2.py` (CP-04, CP-05, CP-07, CP-08, CP-10) continue to pass.
