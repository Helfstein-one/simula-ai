# Handoff Report: Milestone 2 Adversarial Stress Testing

**Verdict**: **REJECT** (CodeParser requires hardening against nested reasoning tags and fence precedence; PytestSandbox is APPROVED)  
**Agent**: Challenger 1 (critic, specialist)  
**Target Modules**: `core/code_parser.py`, `core/sandbox.py`  
**Artifacts Generated**:
- `stress_test_m2.py`: 22-test empirical stress harness
- `stress_test_results.json`: Machine-readable results (18 PASS, 4 DEFECT_CONFIRMED)

---

## 1. Observation

### 1.1 Test Suite Execution
- Running the standalone stress harness `./.venv/bin/python .agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py` executed 22 adversarial test cases:
  - **18 Passed**: All 10 `PytestSandbox` tests passed, both `Security` tests passed, 6 `CodeParser` tests passed.
  - **4 Confirmed Defects**: In `core/code_parser.py` (CP-01, CP-02, CP-03, CP-06).

### 1.2 Observed Defects in `core/code_parser.py`

#### Observation O1: Nested Think Tags Truncation and Draft Code Leakage (CP-01, CP-02)
- In `core/code_parser.py`:
  ```python
  9:  THINK_TAG_REGEX = re.compile(
  10:     r"<think(?:\s+[^>]*)?>.*?</think\s*>",
  11:     flags=re.DOTALL | re.IGNORECASE,
  12: )
  ```
- When input contains nested reasoning tags:
  ```
  <think>thought 1
  <think>thought 1b</think>
  ```python
  def test_bad_draft(): pass
  ```
  </think>
  ```python
  def test_real(): pass
  ```
  ```
- Result from `CodeParser.strip_think_tags`:
  Non-greedy `.*?` matches `<think>thought 1\n<think>thought 1b</think>`.
  The tail `\n```python\ndef test_bad_draft(): pass\n```\n</think>` is left intact in the cleaned text.
- Result from `CodeParser.extract_python_code`:
  `test_bad_draft` is extracted as the target Python code block instead of `test_real`!

#### Observation O2: Think Tag Stripping Mangling Python Literals (CP-03)
- In `core/code_parser.py`:
  ```python
  74: def extract_python_code(cls, response_text: str) -> str:
  76:     cleaned_text = cls.strip_think_tags(response_text)
  ```
- When input contains Python code with `<think>...</think>` in a string literal or comment:
  ```python
  def test_prompt_filter():
      msg = '<think>internal reasoning</think>'
      assert 'internal' in msg
  ```
- Because `strip_think_tags` runs across the raw text before code blocks are isolated, the literal is mangled to `msg = ''`, causing assertion failures or syntax errors.

#### Observation O3: Single Closed Non-Python Block Suppresses Unclosed Python Fallback (CP-06)
- In `core/code_parser.py`:
  ```python
  88: # Exclude explicit non-python blocks if alternatives exist
  89: if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:
  90:     continue
  91: candidates.append(body_clean)
  ```
- When an LLM output contains a single closed bash block followed by an unclosed (truncated) Python block:
  ```markdown
  ```bash
  pytest
  ```
  ```python
  import pytest
  def test_truncated():
      assert 1 == 1
  ```
- Since `len(matches) == 1`, `len(matches) > 1` evaluates to `False`. The non-Python bash block `pytest` is appended to `candidates`.
- Because `candidates` is non-empty (`['pytest']`), fallback `if not candidates:` is skipped, and `extract_python_code` returns `'pytest'` (a bash command string).

### 1.3 Verified Robustness in `core/sandbox.py`
- **SB-01 (Infinite Loop)**: `while True: time.sleep(0.01)` with `timeout_seconds=2` cleanly terminated in `2.01s` with `timed_out=True`, `exit_code=-1`, and `failed_tests=['TIMEOUT']`.
- **SB-02 (Hanging Thread)**: Non-daemon background thread cleanly killed after `2.02s` with `timed_out=True`.
- **SB-03 (Syntax Error)**: Test containing `def test_syntax_err(: pass` resulted in `exit_code=2`, `is_success=False`, with short traceback preserved in `error_summary`.
- **SB-04 (Memory Stress)**: `raise MemoryError` exited with `exit_code=1`, `failed_tests=['test_simulated_oom']`.
- **SB-05 (100GB Allocation)**: Paging exhaustion cleanly timed out without crashing host (`timed_out=True`, `exit_code=-1`).
- **SB-06 (Multi-test Assertions)**: 5 tests (2 passed, 2 assertion failures, 1 KeyError). Exactly the 3 failing tests (`test_bravo_fail`, `test_delta_fail`, `test_echo_error`) were identified; passed tests were excluded.
- **SB-07 (Exit Code 5)**: File with 0 tests returned `exit_code=5` with actionable diagnostic.
- **SB-09 & SB-10 (Isolation & Ephemerality)**: Subprocess cannot contaminate host `os.environ`. Scratch files written in sandbox were deleted with `tmp_dir`.

### 1.4 Security Audit (Zero Host eval/exec)
- **SEC-01 (Static AST Audit)**: AST scan of all 8 modules in `core/` identified **0** calls to `eval()` and **0** calls to `exec()`.
- **SEC-02 (Dynamic Interception)**: Monkeypatched `builtins.eval` and `builtins.exec` during full execution of `CodeParser` and `PytestSandbox`. Exactly **0** invocations originated from `core/`.

---

## 2. Logic Chain

1. **Premise 1**: DeepSeek R1 models frequently output scratchpads and multi-turn reasoning traces. Adversarial prompts, few-shot examples, or self-correction loops can produce nested `<think>` tags.
2. **From Observation O1**: `THINK_TAG_REGEX` is non-greedy and operates in a single pass. When nested `<think>` tags appear, the outer reasoning closure is broken, and internal scratchpad code drafts leak into the candidate pool. In CP-02, this caused `CodeParser` to extract rejected draft code instead of the real generator test suite.
3. **From Observation O2**: Calling `strip_think_tags` before identifying markdown code fences corrupts string literals inside Python code that contain `<think>` text.
4. **From Observation O3**: The guard `len(matches) > 1` at line 89 was intended to handle single blocks, but when the single closed block is explicitly non-Python (`bash`), it prevents fallback to unclosed Python blocks, returning a shell command to the Python sandbox.
5. **From Observation O4**: `PytestSandbox` meets all acceptance criteria, isolating execution, terminating on timeouts, handling syntax errors, and never using host `eval()` or `exec()`.
6. **Conclusion**: While `PytestSandbox` is rock-solid and production-ready, `CodeParser` has 3 reproducible edge-case vulnerabilities that can cause incorrect code extraction and test execution. Therefore, Milestone 2 must be **REJECTED** until `core/code_parser.py` is patched.

---

## 3. Caveats

- **No modifications performed**: Conforming to Challenger constraints, no implementation files in `core/` were modified.
- **Standard DeepSeek R1 paths pass**: Single-level `<think> ... </think>` tags, standard multi-block markdown responses, and pure unclosed Python fences operate correctly and pass all 77 unit/e2e tests in `./.venv/bin/pytest`. The defects surface under adversarial or truncated multi-block inputs.
- **Class-based tests in sandbox**: In `PytestSandbox._parse_failures`, pytest verbose lines for class methods (`simula_temp_test.py::TestClass::test_method FAILED`) currently match the class name `TestClass` in `failed_tests` rather than `test_method`. This does not fail execution, but episodic error reports will reference the class rather than the method name.

---

## 4. Conclusion & Actionable Mitigations

**VERDICT**: **REJECT** Milestone 2 pending hardening of `core/code_parser.py`.

### Required Mitigations for Worker:

1. **Fix Nested Think Tag Stripping (`core/code_parser.py:56-72`)**:
   Implement recursive stripping or greedy/balanced tag stripping, and remove orphaned `</think>` tags:
   ```python
   @staticmethod
   def strip_think_tags(text: str) -> str:
       if not text:
           return ""
       # Iteratively strip innermost think tags until none remain
       prev = None
       cleaned = text
       while prev != cleaned:
           prev = cleaned
           cleaned = THINK_TAG_REGEX.sub("", cleaned)
       
       # Clean any orphaned closing tags
       cleaned = re.sub(r"</think\s*>", "", cleaned, flags=re.IGNORECASE)
       
       # Handle unclosed think tag lookahead
       if "<think" in cleaned.lower():
           if "```" in cleaned:
               cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
           else:
               cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
       return cleaned.strip()
   ```

2. **Fix Non-Python Candidate Filter (`core/code_parser.py:89`)**:
   Remove the `and len(matches) > 1` condition so that explicit non-Python blocks (`bash`, `sql`) are NEVER accepted as Python candidates:
   ```python
   # Replace:
   # if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:
   # With:
   if lang_clean in NON_PYTHON_LANGUAGES:
       continue
   ```

3. **Fence Extraction Before Think Tag Stripping (`core/code_parser.py:74-85`)**:
   Extract code fences from `response_text` first, only stripping think tags outside fenced code, preserving `<think>` literals inside valid Python strings.

---

## 5. Verification Method

To independently reproduce all observations and verify fixes:

```bash
# 1. Run the empirical stress harness
./.venv/bin/python .agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py

# Expected Output:
# CP-01, CP-02, CP-03, CP-06 report [DEFECT_CONFIRMED]
# SB-01 through SB-10 report [PASS]
# SEC-01 and SEC-02 report [PASS]

# 2. View structured JSON report
cat .agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_results.json
```

**Invalidation Conditions**:
The REJECT verdict will be invalidated (and changed to APPROVE) once a worker applies the mitigations above, causing CP-01, CP-02, CP-03, and CP-06 to achieve `[PASS]`, bringing the suite score to 22/22 (100% PASS).
