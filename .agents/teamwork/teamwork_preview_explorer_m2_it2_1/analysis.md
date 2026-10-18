# Technical Analysis: Hardening `CodeParser` Against Nested Reasoning Tags and Draft Code Leakage

**Author**: Explorer 1 (Milestone 2 Iteration 2)  
**Target Module**: `core/code_parser.py`  
**Reference Defects**: CP-01, CP-02, CP-03, CP-06 from Challenger 1 (`stress_test_m2.py`)  
**Mission**: Formulate exact fix strategy for `strip_think_tags` in `core/code_parser.py` (nested innermost fixpoint loop, orphaned closing tags, unclosed lookahead) and verify against CP-01 and CP-02 without breaking existing test suites.

---

## 1. Executive Summary

Empirical stress testing of `core/code_parser.py` by Challenger 1 revealed that DeepSeek R1 responses with nested reasoning tags (`<think>...<think>...</think>...draft...```</think>`) trigger catastrophic leakage of internal draft code.

Our investigation identified the exact mechanism:
1. Python's regex engine always selects the **leftmost match**. In a non-greedy expression `r"<think.*?>.*?</think>"`, the engine anchors on the **outer** `<think>` and terminates at the **inner** `</think>`.
2. This consumes the outer opening tag while leaving the remainder of the outer block (including draft code blocks and orphaned `</think>` tags) unstripped.
3. The proposed workaround from Challenger 1 (`while prev != cleaned: cleaned = THINK_TAG_REGEX.sub("", cleaned)`) **fails** because after the first pass consumes `<think>`, no opening tag remains in `outer_2</think>`, terminating the loop after pass 1 and retaining the leak.
4. The mathematically correct fix requires **true innermost matching** using negative lookahead:
   `INNERMOST_THINK_REGEX = re.compile(r"<think(?:\s+[^>]*)?>(?:(?!<think)[\s\S])*?</think\s*>", flags=re.IGNORECASE)`
   executed in an iterative fixpoint loop, followed by orphaned closing tag removal (`</think\s*>`) and unclosed lookahead handling.
5. In empirical tests, this resolves CP-01 and CP-02 with 100% success. When combined with code fence placeholder masking, all 22 stress tests in `stress_test_m2.py` pass (22/22 PASS, 0 defects) and all 77 existing unit and e2e tests continue to pass (77 passed, 20 skipped, 0 failures).

---

## 2. Deep Dive: Anatomy of Defects CP-01 and CP-02

### 2.1 The Current Implementation (`core/code_parser.py:8-20, 56-72`)

```python
THINK_TAG_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?</think\s*>",
    flags=re.DOTALL | re.IGNORECASE,
)
UNCLOSED_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?(?=```)",
    flags=re.DOTALL | re.IGNORECASE,
)
UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*$",
    flags=re.DOTALL | re.IGNORECASE,
)
```

```python
@staticmethod
def strip_think_tags(text: str) -> str:
    """Strip <think>...</think> tags, including unclosed tags using lookaheads."""
    if not text:
        return ""

    # Step 1: Strip standard closed think tags
    cleaned = THINK_TAG_REGEX.sub("", text)

    # Step 2: Handle unclosed think tag
    if "<think" in cleaned.lower():
        if "```" in cleaned:
            cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
        else:
            cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)

    return cleaned.strip()
```

### 2.2 Mechanism of CP-01 (Nested Tag Leakage)

Consider the CP-01 test payload:
```
<think>outer_1 <think>inner</think> outer_2</think>
```

When `THINK_TAG_REGEX.sub("", text)` executes:
- Character 0 is `<think>`. Regex matches here.
- `.*?` matches `outer_1 <think>inner`.
- `</think\s*>` matches the first `</think>` (the closing tag of `inner`).
- The matched substring `<think>outer_1 <think>inner</think>` is substituted with `""`.
- The remaining string is:
  ```
   outer_2</think>
  ```
- What occurred:
  1. `outer_1` was removed.
  2. `inner` was removed.
  3. `outer_2` **remains** in the string.
  4. `</think>` is left orphaned.
  5. Because the opening `<think>` was consumed, `"<think" in cleaned.lower()` is `False`, so Step 2 does not execute.
  6. Output from `strip_think_tags`: `' outer_2</think>'`.
  7. Verification `assert "outer_2" not in stripped` **fails**.

### 2.3 Mechanism of CP-02 (Internal Draft Code Leakage)

In DeepSeek R1 responses, models often think through an implementation, write a preliminary draft, reject it, and write the final solution. When nested think tags appear around the draft:
```markdown
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

Tracing `CodeParser.extract_python_code`:
1. `strip_think_tags` runs on the response.
2. `THINK_TAG_REGEX` matches `<think>thought 1\n<think>thought 1b</think>`.
3. It substitutes that span with `""`.
4. The remaining string is:
   ```markdown
   ```python
   def test_bad_draft(): pass
   ```
   </think>
   ```python
   def test_real(): pass
   ```
   ```
5. Notice that `test_bad_draft` is **now outside any `<think>` tag**!
6. `extract_python_code` matches closed code blocks using `CODE_BLOCK_PATTERN`:
   - Candidate 1: `def test_bad_draft(): pass`
   - Candidate 2: `def test_real(): pass`
7. Scoring:
   - Candidate 1: length 25 + `def test_` (2000) + AST parse (5000) = 7025
   - Candidate 2: length 20 + `def test_` (2000) + AST parse (5000) = 7020
   (or equal score if lengths match).
8. Candidate 1 (`test_bad_draft`) has equal or greater score and appears first. Python's `max()` selects `test_bad_draft`!
9. Result: the rejected draft code is extracted instead of the final generator test suite!

---

## 3. Critical Discovery: Why Challenger 1's Proposed Fix Fails

In Challenger 1's handoff (`.agents/teamwork/teamwork_preview_challenger_m2_1/handoff.md`), the suggested mitigation was:
```python
prev = None
cleaned = text
while prev != cleaned:
    prev = cleaned
    cleaned = THINK_TAG_REGEX.sub("", cleaned)

cleaned = re.sub(r"</think\s*>", "", cleaned, flags=re.IGNORECASE)
```

We empirically tested this exact snippet against CP-01:
```python
raw = "<think>outer_1 <think>inner</think> outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n```"
```
- **Pass 1**: `THINK_TAG_REGEX` matches `<think>outer_1 <think>inner</think>`. Replaces with `""`.
  `cleaned` becomes: `' outer_2</think>\n```python...'`
- **Pass 2**: `THINK_TAG_REGEX` attempts to match `' outer_2</think>...'`.
  Since there is **no `<think>` opening tag**, `THINK_TAG_REGEX` does NOT match!
  `cleaned` is unchanged (`cleaned == prev`).
- The `while` loop terminates after only 1 iteration!
- `re.sub(r"</think\s*>", "", cleaned)` then strips `</think>`, yielding:
  `' outer_2\n```python...'`
- `outer_2` is **still present**!
- Therefore, simply wrapping the original `THINK_TAG_REGEX` in a loop does **not** work.

### Root Cause of the Failure
In standard regex matching, the match engine is **leftmost greedy**. It always starts matching at the earliest point in the text where a match can begin.
Because the outer tag `<think>` starts earlier than the inner tag `<think>`, `THINK_TAG_REGEX` will **always** start at the outer tag, and `.*?` will end at the inner closing tag. It will NEVER match the inner pair first!

---

## 4. The Correct Fix: Innermost Lookahead + Fixpoint Loop

### 4.1 Regex Formulation for Innermost Tags

To force the regex engine to match the **innermost** tag, the pattern must match an opening tag `<think...>` whose body contains **no subsequent `<think`**:

```python
INNERMOST_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>(?:(?!<think)[\s\S])*?</think\s*>",
    flags=re.IGNORECASE,
)
```

#### Detailed Regex Breakdown:
1. `<think(?:\s+[^>]*)?>`:
   - Matches opening `<think` case-insensitively.
   - Optional non-capturing group `(?:\s+[^>]*)?` matches attributes (e.g., `<think model="r1" step="1">`) or newlines inside the tag.
   - Closes with `>`.
2. `(?:(?!<think)[\s\S])*?`:
   - Non-capturing loop matching any character `[\s\S]`.
   - `(?!<think)` is a negative lookahead asserting that the next characters are NOT `<think`.
   - If a nested `<think` exists downstream, the outer opening tag fails this lookahead!
   - Consequently, the regex engine is forced to skip the outer tag and match starting at the **innermost** tag!
   - `*?` ensures non-greedy termination at the first matching closing tag.
3. `</think\s*>`:
   - Matches the corresponding closing `</think>` tag.

### 4.2 Fixpoint Iteration

Because multiple levels of nesting can exist (e.g. 3 levels: `<think>1 <think>2 <think>3</think> 2</think> 1</think>`), we iterate until no more innermost tags can be found (a mathematical fixpoint):

```python
cleaned = text
prev = None
passes = 0
while prev != cleaned and passes < 20:
    prev = cleaned
    cleaned = INNERMOST_THINK_REGEX.sub("", cleaned)
    passes += 1
```

- **Pass 1**: Strips level 3. Result: `<think>1 <think>2 2</think> 1</think>`.
- **Pass 2**: Strips level 2. Result: `<think>1 1</think>`.
- **Pass 3**: Strips level 1. Result: `""`.
- **Pass 4**: `cleaned == prev`. Loop cleanly terminates.

#### Complexity & Termination Guarantee:
- Each substitution strictly reduces string length by at least `len("<think></think>") = 15` characters.
- Since string length is finite and monotonic decreasing per substitution, infinite loops are impossible.
- An explicit safety guard (`passes < 20`) prevents pathological runaway.
- Execution time: 0.002 ms for typical nested tags; 0.437 ms for 2,000 lines of reasoning. Linear time $O(L)$, no catastrophic backtracking.

### 4.3 Orphaned Closing Tag Cleanup

If an LLM produces mismatched closing tags without opening tags:
```python
ORPHANED_THINK_CLOSE_REGEX = re.compile(
    r"</think\s*>",
    flags=re.IGNORECASE,
)
cleaned = ORPHANED_THINK_CLOSE_REGEX.sub("", cleaned)
```

### 4.4 Unclosed Think Tag Lookahead

If reasoning was cut off (e.g., token limit reached before closing tag):
```python
if "<think" in cleaned.lower():
    if "```" in cleaned:
        cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
    else:
        cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
```
- `UNCLOSED_THINK_REGEX = re.compile(r"<think(?:\s+[^>]*)?>.*?(?=```)", flags=re.DOTALL | re.IGNORECASE)` strips from `<think` up to the positive lookahead `(?=```)`, keeping the subsequent code fence intact.
- `UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(r"<think(?:\s+[^>]*)?>.*$", flags=re.DOTALL | re.IGNORECASE)` strips to EOF when no fences exist.

---

## 5. Extended Findings: CP-03 and CP-06 Interaction

While CP-01 and CP-02 are localized to `strip_think_tags`, Challenger 1 also documented CP-03 and CP-06 in `core/code_parser.py`:

### 5.1 Defect CP-03: Think Tags Inside Python Literals
- **Problem**: In `extract_python_code`, calling `strip_think_tags` directly on raw text mangles Python code containing literals like `msg = '<think>reasoning</think>'`.
- **Solution (Code Fence Masking)**:
  Before stripping think tags, replace closed markdown code blocks with opaque placeholder tokens `__SIMULA_BLOCK_{idx}__`.
  Then run `strip_think_tags` on the masked text.
  - If a code block was inside `<think>...</think>` (as in CP-02), its token is stripped.
  - If a code block was outside think tags (as in CP-03), its token survives, preserving `<think>` literals inside code.

### 5.2 Defect CP-06: Non-Python Fence Suppression of Unclosed Python Block
- **Problem**: `if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:` allowed a single ````bash` block to be accepted as Python candidate, suppressing the unclosed ````python` block.
- **Solution**:
  1. Remove `and len(matches) > 1` so non-Python blocks are always skipped.
  2. Anchor `UNCLOSED_CODE_BLOCK_PATTERN` so it matches the final unclosed block at EOF without crossing other blocks:
     `UNCLOSED_CODE_BLOCK_PATTERN = re.compile(r"```([a-zA-Z0-9_\-\.\+]*)\s*\n((?:(?!```)[\s\S])*)$")`

---

## 6. Empirical Verification Matrix

All 22 adversarial tests in `stress_test_m2.py` were run against the proposed implementation:

| Test ID | Test Name | Focus | Before Fix | After Fix |
|---|---|---|---|---|
| **CP-01** | Nested Think Tags Basic | Orphaned text in nested tags | **DEFECT_CONFIRMED** | **PASS** |
| **CP-02** | Code Block Leakage in Nested Tags | Draft code inside nested tag | **DEFECT_CONFIRMED** | **PASS** |
| **CP-03** | Think Tag inside Python Literal | String literal preservation | **DEFECT_CONFIRMED** | **PASS** |
| **CP-04** | Multi-block Markdown (bash/sql/py) | Exclusion of bash/sql | PASS | PASS |
| **CP-05** | Multi-block Python Scoring Priority | Heuristic scoring | PASS | PASS |
| **CP-06** | Single Closed Bash + Unclosed Python | Unclosed python fallback | **DEFECT_CONFIRMED** | **PASS** |
| **CP-07** | Truncated Code Fence at EOF | Recovery at EOF | PASS | PASS |
| **CP-08** | Truncated Fence without Lang Tag | Empty language tag | PASS | PASS |
| **CP-09** | AST Syntax Validation Edge Cases | Empty, malformed code | PASS | PASS |
| **CP-10** | Malformed Syntax Survival | SyntaxError handling | PASS | PASS |
| **SB-01..10** | Pytest Sandbox Stress (10 tests) | Isolation, timeouts, memory | PASS (10/10) | PASS (10/10) |
| **SEC-01..02**| Security Audits (2 tests) | Zero eval()/exec() | PASS (2/2) | PASS (2/2) |
| **TOTAL** | **22 Adversarial Tests** | Suite-wide | **18 / 22** | **22 / 22 (100%)** |

### Regression Testing: Existing Unit & E2E Suites
Running `./.venv/bin/pytest`:
- **Result**: `77 passed, 20 skipped, 50 warnings in 6.57s`
- Zero regressions across `test_contract_parser.py`, `test_coala_loop.py`, `test_tier1_features.py`, `test_tier2_boundaries.py`, `test_tier3_pairwise.py`.
