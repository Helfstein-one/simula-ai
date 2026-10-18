import re
import ast

INNER_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>((?:(?!<think\b).)*?)</think\s*>",
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

CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*?)```",
    flags=re.DOTALL,
)
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*)$",
    flags=re.DOTALL,
)

NON_PYTHON_LANGUAGES = {
    "bash", "sh", "zsh", "shell", "yaml", "yml", "json",
    "sql", "html", "xml", "css", "markdown", "md", "text", "txt", "diff",
}

def strip_think_tags(text: str) -> str:
    """Robust think tag stripping (Explorer 1 specification)."""
    if not text:
        return ""
    prev = None
    cleaned = text
    while prev != cleaned:
        prev = cleaned
        cleaned = INNER_THINK_REGEX.sub("", cleaned)
    
    cleaned = re.sub(r"</think\s*>", "", cleaned, flags=re.IGNORECASE)
    
    if "<think" in cleaned.lower():
        if "```" in cleaned:
            cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
        else:
            cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
    return cleaned.strip()


def find_all_code_blocks(text: str):
    """Find all code blocks, both closed and unclosed."""
    blocks = []
    for m in CODE_BLOCK_PATTERN.finditer(text):
        blocks.append({
            "start": m.start(),
            "end": m.end(),
            "lang": m.group(1).strip().lower(),
            "body": m.group(2),
            "closed": True,
        })
    last_end = blocks[-1]["end"] if blocks else 0
    remaining = text[last_end:]
    unclosed_m = UNCLOSED_CODE_BLOCK_PATTERN.search(remaining)
    if unclosed_m:
        blocks.append({
            "start": last_end + unclosed_m.start(),
            "end": len(text),
            "lang": unclosed_m.group(1).strip().lower(),
            "body": unclosed_m.group(2),
            "closed": False,
        })
    return blocks


def extract_python_code(response_text: str) -> str:
    if not response_text:
        return ""

    # Step 1: Identify all code blocks (closed & unclosed)
    blocks = find_all_code_blocks(response_text)

    # Step 2: If code blocks exist, isolate their bodies using placeholders
    if blocks:
        pieces = []
        last_pos = 0
        for i, b in enumerate(blocks):
            pieces.append(response_text[last_pos:b["start"]])
            token = f"__SIMULA_CODE_BLOCK_{i}__"
            if b["closed"]:
                pieces.append(f"```{b['lang']}\n{token}\n```")
            else:
                pieces.append(f"```{b['lang']}\n{token}")
            last_pos = b["end"]
        pieces.append(response_text[last_pos:])
        masked_text = "".join(pieces)
    else:
        masked_text = response_text

    # Step 3: Strip think tags outside isolated code blocks
    cleaned_text = strip_think_tags(masked_text)

    # Step 4: Collect candidates that survived think tag stripping
    candidates: list[str] = []
    if blocks:
        # First priority: closed blocks that are not non-python
        closed_candidates = []
        unclosed_candidates = []
        for i, b in enumerate(blocks):
            token = f"__SIMULA_CODE_BLOCK_{i}__"
            if token not in cleaned_text:
                # Stripped because it was inside a <think> tag
                continue
            if b["lang"] in NON_PYTHON_LANGUAGES:
                continue
            body_clean = b["body"].strip()
            if not body_clean:
                continue
            if b["closed"]:
                closed_candidates.append(body_clean)
            else:
                unclosed_candidates.append(body_clean)

        candidates = closed_candidates if closed_candidates else unclosed_candidates

    # Step 5: Heuristic scoring for candidate selection
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

    # Step 6: Fallback to raw un-fenced code
    lines = cleaned_text.splitlines()
    first_code_idx = -1
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ", "def ", "class ", "#!")):
            first_code_idx = idx
            break

    if first_code_idx != -1:
        return "\n".join(lines[first_code_idx:]).strip()

    return cleaned_text.strip()


# Test CP-01
raw_cp1 = "<think>outer_1 <think>inner</think> outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n```"
res_cp1 = extract_python_code(raw_cp1)
assert "def test_ok" in res_cp1, f"CP-01 failed: {res_cp1}"
print("CP-01 PASSED")

# Test CP-02
raw_cp2 = '''<think>thought 1
<think>thought 1b</think>
```python
def test_bad_draft(): pass
```
</think>
```python
def test_real(): pass
```'''
res_cp2 = extract_python_code(raw_cp2)
assert "test_real" in res_cp2, f"CP-02 failed: {res_cp2}"
assert "test_bad_draft" not in res_cp2, f"CP-02 leaked: {res_cp2}"
print("CP-02 PASSED")

# Test CP-03
raw_cp3 = '''Here is the generator test:
```python
def test_prompt_filter():
    msg = '<think>internal reasoning</think>'
    assert 'internal' in msg
```
'''
res_cp3 = extract_python_code(raw_cp3)
assert "internal reasoning" in res_cp3, f"CP-03 failed: {res_cp3}"
print("CP-03 PASSED")

# Test CP-04
raw_cp4 = '''### Step 1: Install
```bash
pip install faker pytest
```
### Step 2: Schema
```sql
CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));
```
### Step 3: Test
```python
import pytest
def test_user_creation():
    assert True
```
'''
res_cp4 = extract_python_code(raw_cp4)
assert "test_user_creation" in res_cp4, f"CP-04 failed: {res_cp4}"
assert "pip install" not in res_cp4
print("CP-04 PASSED")

# Test CP-05
raw_cp5 = '''Here is a snippet:
```python
x = 42
```
And here is the complete validation suite:
```python
import pytest
from faker import Faker

def test_data_generation():
    fake = Faker()
    assert fake.name() is not None
```
'''
res_cp5 = extract_python_code(raw_cp5)
assert "test_data_generation" in res_cp5, f"CP-05 failed: {res_cp5}"
assert "x = 42" not in res_cp5
print("CP-05 PASSED")

# Test CP-06
raw_cp6 = '''Run this command:
```bash
pytest
```
Here is the test code:
```python
import pytest
def test_truncated():
    assert 1 == 1
'''
res_cp6 = extract_python_code(raw_cp6)
assert "test_truncated" in res_cp6, f"CP-06 failed: {res_cp6}"
print("CP-06 PASSED")

# Test CP-07
raw_cp7 = '''Code generation output:
```python
import pytest

def test_alpha():
    assert True
'''
res_cp7 = extract_python_code(raw_cp7)
assert "test_alpha" in res_cp7, f"CP-07 failed: {res_cp7}"
print("CP-07 PASSED")

# Test CP-08
raw_cp8 = '''Code generation output:
```
import pytest
def test_beta():
    assert 42 == 42
'''
res_cp8 = extract_python_code(raw_cp8)
assert "test_beta" in res_cp8, f"CP-08 failed: {res_cp8}"
print("CP-08 PASSED")

# Test Unclosed think tag before closed code fence containing <think> literal
raw_unclosed_both = '''<think>
Unclosed reasoning before code fence
```python
import pytest
def test_combined():
    literal = '<think>my tag</think>'
    assert literal is not None
```
'''
res_unclosed_both = extract_python_code(raw_unclosed_both)
assert "Unclosed reasoning" not in res_unclosed_both, f"Unclosed reasoning leaked: {res_unclosed_both}"
assert "my tag" in res_unclosed_both, f"Literal tag missing: {res_unclosed_both}"
print("Unclosed think before fence with literal inside code PASSED")

# Test Unclosed think tag before UNCLOSED code fence containing <think> literal
raw_unclosed_eof = '''<think>
Unclosed reasoning before code fence
```python
import pytest
def test_combined_unclosed():
    literal = '<think>my tag</think>'
    assert literal is not None
'''
res_unclosed_eof = extract_python_code(raw_unclosed_eof)
assert "Unclosed reasoning" not in res_unclosed_eof, f"Unclosed reasoning leaked: {res_unclosed_eof}"
assert "my tag" in res_unclosed_eof, f"Literal tag missing: {res_unclosed_eof}"
print("Unclosed think before UNCLOSED code fence PASSED")

# Test raw un-fenced code fallback
raw_unfenced = '''import pytest
def test_direct():
    msg = '<think>literal in raw</think>'
    assert True
'''
res_unfenced = extract_python_code(raw_unfenced)
assert "test_direct" in res_unfenced, f"Raw fallback failed: {res_unfenced}"
print("Raw unfenced code fallback PASSED")
