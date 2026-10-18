import re
import ast

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

def strip_think_tags_v2(text: str) -> str:
    """Explorer 1's hardened strip_think_tags."""
    if not text:
        return ""
    prev = None
    cleaned = text
    while prev != cleaned:
        prev = cleaned
        cleaned = THINK_TAG_REGEX.sub("", cleaned)
    
    cleaned = re.sub(r"</think\s*>", "", cleaned, flags=re.IGNORECASE)
    
    if "<think" in cleaned.lower():
        if "```" in cleaned:
            cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
        else:
            cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)
    return cleaned.strip()


def extract_python_code_candidate_1(response_text: str) -> str:
    """Strategy 1: Mask code block bodies with unique placeholders before think tag stripping."""
    if not response_text:
        return ""

    placeholders: dict[str, str] = {}
    counter = 0

    def _mask_closed(match: re.Match) -> str:
        nonlocal counter
        lang = match.group(1)
        body = match.group(2)
        token = f"__SIMULA_BLOCK_{counter}__"
        counter += 1
        placeholders[token] = body
        return f"```{lang}\n{token}\n```"

    # Step 1: Mask closed code blocks
    masked_text = CODE_BLOCK_PATTERN.sub(_mask_closed, response_text)

    # Step 2: Mask unclosed code block if present
    def _mask_unclosed(match: re.Match) -> str:
        nonlocal counter
        lang = match.group(1)
        body = match.group(2)
        token = f"__SIMULA_BLOCK_{counter}__"
        counter += 1
        placeholders[token] = body
        return f"```{lang}\n{token}"

    # Only mask unclosed if there is an unclosed block at end of text
    # Note: after closed blocks are replaced, check for unclosed fence
    # To avoid double-matching closed blocks, we check the tail
    last_closing = masked_text.rfind("```")
    # If the last ``` starts an unclosed block (i.e. not closed), mask it
    # We can use UNCLOSED_CODE_BLOCK_PATTERN if the tail has an unclosed block
    
    # Step 3: Strip think tags from masked text
    cleaned_text = strip_think_tags_v2(masked_text)

    # Step 4: Extract closed code blocks from cleaned text
    matches = CODE_BLOCK_PATTERN.findall(cleaned_text)

    candidates: list[str] = []
    if matches:
        for lang, token_or_body in matches:
            lang_clean = lang.strip().lower()
            token_clean = token_or_body.strip()
            body_clean = placeholders.get(token_clean, token_clean).strip()
            if not body_clean:
                continue
            # CP-06 fix: unconditional exclude non-python
            if lang_clean in NON_PYTHON_LANGUAGES:
                continue
            candidates.append(body_clean)

    # Step 5: Fallback to unclosed code block if no candidates
    if not candidates:
        unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(cleaned_text)
        for lang, token_or_body in unclosed_matches:
            lang_clean = lang.strip().lower()
            token_clean = token_or_body.strip()
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


# Test CP-03
raw_cp3 = '''Here is the generator test:
```python
def test_prompt_filter():
    msg = '<think>internal reasoning</think>'
    assert 'internal' in msg
```
'''
res_cp3 = extract_python_code_candidate_1(raw_cp3)
print("CP-03 result:")
print(res_cp3)
assert "internal reasoning" in res_cp3, "CP-03 failed: internal reasoning was stripped!"
print("CP-03 PASSED!\n")

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
res_cp2 = extract_python_code_candidate_1(raw_cp2)
print("CP-02 result:", res_cp2)
assert "test_real" in res_cp2, "CP-02 failed: test_real not extracted!"
assert "test_bad_draft" not in res_cp2, "CP-02 failed: test_bad_draft leaked!"
print("CP-02 PASSED!\n")

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
res_cp6 = extract_python_code_candidate_1(raw_cp6)
print("CP-06 result:", res_cp6)
assert "test_truncated" in res_cp6, "CP-06 failed: test_truncated not extracted!"
print("CP-06 PASSED!\n")

# Test unclosed think tag before code fence
raw_unclosed_think = '''<think>
some unclosed reasoning before code fence
```python
def test_with_think_inside():
    s = '<think>my tag</think>'
    assert True
```
'''
res_unclosed = extract_python_code_candidate_1(raw_unclosed_think)
print("Unclosed think before fence result:", res_unclosed)
assert "unclosed reasoning" not in res_unclosed, "Unclosed think reasoning was not stripped!"
assert "my tag" in res_unclosed, "Literal inside code was stripped!"
print("Unclosed think before fence PASSED!\n")
