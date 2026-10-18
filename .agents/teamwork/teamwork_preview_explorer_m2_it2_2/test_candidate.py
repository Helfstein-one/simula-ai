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


def extract_python_code(response_text: str) -> str:
    if not response_text:
        return ""

    placeholders: dict[str, str] = {}

    def _mask_closed(match: re.Match) -> str:
        lang = match.group(1)
        body = match.group(2)
        token = f"__SIMULA_CODE_BLOCK_{len(placeholders)}__"
        placeholders[token] = body
        return f"```{lang}\n{token}\n```"

    # Mask closed code blocks
    masked_text = CODE_BLOCK_PATTERN.sub(_mask_closed, response_text)

    # Check for unclosed code block after the last closed fence (if any)
    # If the text still contains an unclosed fence at EOF
    def _mask_unclosed(match: re.Match) -> str:
        lang = match.group(1)
        body = match.group(2)
        token = f"__SIMULA_CODE_BLOCK_{len(placeholders)}__"
        placeholders[token] = body
        return f"```{lang}\n{token}"

    # Only attempt unclosed masking on the portion after the last closed fence
    last_fence = masked_text.rfind("```")
    # If there is an odd number of ``` fences or an unclosed fence at EOF:
    # A simple check: if the suffix after last_fence starts an unclosed fence
    # Actually, if we search from last_fence or from start:
    # If last_fence == -1 (no closed fences at all), or after last_fence:
    suffix_start = last_fence + 3 if last_fence != -1 else 0
    suffix = masked_text[suffix_start:]
    unclosed_match = UNCLOSED_CODE_BLOCK_PATTERN.search(suffix)
    if unclosed_match:
        # replace the unclosed block in masked_text
        match_start = suffix_start + unclosed_match.start()
        lang = unclosed_match.group(1)
        body = unclosed_match.group(2)
        token = f"__SIMULA_CODE_BLOCK_{len(placeholders)}__"
        placeholders[token] = body
        masked_text = masked_text[:match_start] + f"```{lang}\n{token}"

    # Strip think tags outside isolated code blocks
    cleaned_text = strip_think_tags(masked_text)

    # Extract closed candidates
    matches = CODE_BLOCK_PATTERN.findall(cleaned_text)
    candidates: list[str] = []
    if matches:
        for lang, body_or_token in matches:
            lang_clean = lang.strip().lower()
            token_clean = body_or_token.strip()
            body_clean = placeholders.get(token_clean, token_clean).strip()
            if not body_clean:
                continue
            if lang_clean in NON_PYTHON_LANGUAGES:
                continue
            candidates.append(body_clean)

    # Extract unclosed candidates if no closed candidates
    if not candidates:
        unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(cleaned_text)
        for lang, body_or_token in unclosed_matches:
            lang_clean = lang.strip().lower()
            token_clean = body_or_token.strip()
            body_clean = placeholders.get(token_clean, token_clean).strip()
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

# Test Unclosed think tag before code fence containing <think> literal
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
