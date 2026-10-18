# Handoff Report: Hardening `strip_think_tags` & CodeParser Fix Strategy

**Verdict**: **READY_FOR_IMPLEMENTATION**  
**Role**: Explorer 1 (Milestone 2 Iteration 2)  
**Target Module**: `core/code_parser.py`  
**Reference Artifacts**:
- `analysis.md`: In-depth theoretical and empirical analysis
- `proposed_code_parser.patch`: Drop-in unified patch for implementer
- Challenger 1 handoff: `.agents/teamwork/teamwork_preview_challenger_m2_1/handoff.md`
- Stress harness: `.agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py`

---

## 1. Observation

### 1.1 Direct Defect Observations in `stress_test_m2.py`
Executing `./.venv/bin/python .agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py` reproduced:
- **CP-01**: `[DEFECT_CONFIRMED] Nested Think Tags Stripping Leakage`
  - Input: `<think>outer_1 <think>inner</think> outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n````
  - Verbatim error: `Regex non-greedy left orphaned inner-outer text: 'outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n```'`
- **CP-02**: `[DEFECT_CONFIRMED] Code Block Leakage in Nested Think Tags`
  - Verbatim error: `Draft code inside nested <think> was extracted instead of outer final code due to regex non-greedy match truncation.`
- **CP-03**: `[DEFECT_CONFIRMED] Think Tag inside Python String Literal`
  - Verbatim error: `strip_think_tags ran prior to code extraction and mangled Python string literal: valid=True, err=None`
- **CP-06**: `[DEFECT_CONFIRMED] Single Closed Non-Python + Unclosed Python`
  - Verbatim error: `When exactly 1 closed block exists and is bash, CodeParser returns bash instead of evaluating unclosed python block.`

### 1.2 Verbatim Code in `core/code_parser.py`
In `core/code_parser.py`:
- Lines 9-12:
  ```python
  THINK_TAG_REGEX = re.compile(
      r"<think(?:\s+[^>]*)?>.*?</think\s*>",
      flags=re.DOTALL | re.IGNORECASE,
  )
  ```
- Lines 56-71:
  ```python
  @staticmethod
  def strip_think_tags(text: str) -> str:
      if not text:
          return ""
      cleaned = THINK_TAG_REGEX.sub("", text)
      if "<think" in cleaned.lower():
          if "```" in cleaned:
              cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
          else:
              cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
      return cleaned.strip()
  ```

### 1.3 Direct Observation on Challenger 1's Proposed Fix
Running Challenger 1's proposed `while prev != cleaned: cleaned = THINK_TAG_REGEX.sub("", cleaned)` on CP-01 payload demonstrated that the loop terminates after exactly 1 pass:
- Pass 1 substitutes `<think>outer_1 <think>inner</think>` with `""`.
- The remaining text ` outer_2</think>` contains no opening `<think>` tag, so `THINK_TAG_REGEX` produces zero matches on Pass 2.
- The loop exits immediately. `outer_2` is not stripped. Challenger's naive loop does not fix CP-01.

---

## 2. Logic Chain

1. **Premise**: In regular expressions, matching is leftmost-first. In `<think>outer <think>inner</think> tail</think>`, the non-greedy pattern `r"<think.*?>.*?</think>"` anchors at the outer `<think>` and stops at the inner `</think>`.
2. **From Observation 1.1 & 1.2**: Replacing `<think>outer <think>inner</think>` with `""` leaves ` tail</think>` in the text.
3. **From Observation 1.3**: Wrapping `THINK_TAG_REGEX.sub` in a `while prev != cleaned:` loop fails because `tail</think>` has no opening `<think>` tag, so subsequent passes match nothing.
4. **Resolution for Innermost Matching**: To match innermost tags, the opening tag must assert that no other `<think` occurs before `</think>`. The regex `r"<think(?:\s+[^>]*)?>(?:(?!<think)[\s\S])*?</think\s*>"` achieves this via negative lookahead `(?!<think)`.
5. **Fixpoint Loop**: Running `INNERMOST_THINK_REGEX.sub("", cleaned)` in a `while prev != cleaned:` loop iteratively strips innermost pairs from deepest to shallowest until fixpoint is reached.
6. **Orphaned Tags & Lookaheads**: Any orphaned `</think\s*>` tags are stripped next. Finally, unclosed tags are cleaned using lookahead to ```` ` (`(?=```)`).
7. **Empirical Result**: Applying this logic transforms CP-01 and CP-02 from `[DEFECT_CONFIRMED]` to `[PASS]`. Combined with code block placeholder masking in `extract_python_code`, the stress suite achieves 22/22 (100% PASS) with 0 regressions in pytest (77/77 PASS).

---

## 3. Caveats

- **Explorer Read-Only Constraint**: In compliance with the Teamwork Explorer contract, no project files in `core/` were modified. Implementation must be performed by the worker agent.
- **Max Iterations Guard**: While string reduction guarantees termination, the fix includes a defensive limit of `passes < 20` to prevent infinite loops on pathological inputs.
- **Literal Think Tags in Code (CP-03)**: Addressing CP-01 and CP-02 via `strip_think_tags` directly resolves nested and unclosed think tags. However, preserving literal `<think>` tags inside Python strings (CP-03) and unclosed Python fallback (CP-06) requires the accompanying updates in `extract_python_code` and `UNCLOSED_CODE_BLOCK_PATTERN` provided in `proposed_code_parser.patch`.

---

## 4. Conclusion & Actionable Mitigations

### 4.1 Recommended Implementation for Worker Agent

#### Change 1: Update Regex Definitions in `core/code_parser.py` (lines 8-20, 27-30)
```python
# Regex for stripping reasoning tags (handles nested, closed, orphaned, unclosed lookahead)
INNERMOST_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>(?:(?!<think)[\s\S])*?</think\s*>",
    flags=re.IGNORECASE,
)
ORPHANED_THINK_CLOSE_REGEX = re.compile(
    r"</think\s*>",
    flags=re.IGNORECASE,
)
THINK_TAG_REGEX = INNERMOST_THINK_REGEX  # Backward compatibility alias
UNCLOSED_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*?(?=```)",
    flags=re.DOTALL | re.IGNORECASE,
)
UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>.*$",
    flags=re.DOTALL | re.IGNORECASE,
)

# Unclosed code block pattern anchored to EOF without crossing other fences
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n((?:(?!```)[\s\S])*)$"
)
```

#### Change 2: Update `strip_think_tags` in `core/code_parser.py` (lines 56-72)
```python
    @staticmethod
    def strip_think_tags(text: str) -> str:
        """Strip <think>...</think> tags, including nested and unclosed tags."""
        if not text:
            return ""

        # Step 1: Iteratively strip innermost closed think tags until fixpoint
        cleaned = text
        prev = None
        passes = 0
        while prev != cleaned and passes < 20:
            prev = cleaned
            cleaned = INNERMOST_THINK_REGEX.sub("", cleaned)
            passes += 1

        # Step 2: Clean any orphaned closing tags
        cleaned = ORPHANED_THINK_CLOSE_REGEX.sub("", cleaned)

        # Step 3: Handle unclosed think tag lookaheads
        if "<think" in cleaned.lower():
            if "```" in cleaned:
                cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
            else:
                cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)

        return cleaned.strip()
```

#### Change 3: Update `extract_python_code` in `core/code_parser.py` (lines 74-125)
Mask closed code blocks using temporary placeholders `__SIMULA_BLOCK_{idx}__` before stripping think tags, and exclude non-Python blocks uniformly:
```python
    @classmethod
    def extract_python_code(cls, response_text: str) -> str:
        """Strip reasoning tags and extract the primary executable Python code block."""
        blocks: list[tuple[str, str]] = []
        def _repl(m: re.Match) -> str:
            idx = len(blocks)
            blocks.append((m.group(1), m.group(2)))
            return f"__SIMULA_BLOCK_{idx}__"

        masked_text = CODE_BLOCK_PATTERN.sub(_repl, response_text)
        cleaned_masked = cls.strip_think_tags(masked_text)

        candidates: list[str] = []
        for idx, (lang, body) in enumerate(blocks):
            token = f"__SIMULA_BLOCK_{idx}__"
            if token in cleaned_masked:
                lang_clean = lang.strip().lower()
                body_clean = body.strip()
                if not body_clean:
                    continue
                if lang_clean in NON_PYTHON_LANGUAGES:
                    continue
                candidates.append(body_clean)

        if not candidates:
            restored_text = cleaned_masked
            for idx, (lang, body) in enumerate(blocks):
                restored_text = restored_text.replace(f"__SIMULA_BLOCK_{idx}__", f"```{lang}\n{body}```")
            unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(restored_text)
            for lang, body in unclosed_matches:
                lang_clean = lang.strip().lower()
                body_clean = body.strip()
                if body_clean and lang_clean not in NON_PYTHON_LANGUAGES:
                    candidates.append(body_clean)

        if candidates:
            def _score_candidate(block: str) -> int:
                score = len(block)
                if "import " in block or "from " in block:
                    score += 1000
                if "def test_" in block:
                    score += 2000
                elif "def " in block:
                    score += 500
                if "class " in block:
                    score += 200
                try:
                    ast.parse(block)
                    score += 5000
                except SyntaxError:
                    pass
                return score

            return max(candidates, key=_score_candidate).strip()

        # Fallback: Raw un-fenced code
        lines = cleaned_masked.splitlines()
        first_code_idx = -1
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("import ", "from ", "def ", "class ", "#!")):
                first_code_idx = idx
                break

        if first_code_idx != -1:
            return "\n".join(lines[first_code_idx:]).strip()

        return cleaned_masked.strip()
```

---

## 5. Verification Method

To independently verify after the worker applies the patch:

```bash
# 1. Apply patch
git apply .agents/teamwork/teamwork_preview_explorer_m2_it2_1/proposed_code_parser.patch

# 2. Run adversarial stress suite
./.venv/bin/python .agents/teamwork/teamwork_preview_challenger_m2_1/stress_test_m2.py

# Expected Output:
# TOTAL TESTS: 22 | PASSED: 22 | DEFECTS/FINDINGS CONFIRMED: 0

# 3. Run full unit and e2e test suite
./.venv/bin/pytest

# Expected Output:
# 77 passed, 20 skipped in ~7s
```

**Invalidation Conditions**:
This analysis is invalidated if:
1. `INNERMOST_THINK_REGEX` fails on valid DeepSeek R1 responses with unusual whitespace or attributes in `<think>` tags (tested: attributes and multiline tags pass).
2. The fixpoint loop exceeds 20 passes on non-pathological responses.
3. Existing pytest tests fail on valid single-level or unclosed tags.
