import re

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

def strip_think_tags_v2(text: str) -> str:
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

raw_cp2 = '''<think>thought 1
<think>thought 1b</think>
```python
def test_bad_draft(): pass
```
</think>
```python
def test_real(): pass
```'''

placeholders = {}
counter = 0
def _mask_closed(match):
    global counter
    lang = match.group(1)
    body = match.group(2)
    token = f"__SIMULA_BLOCK_{counter}__"
    counter += 1
    placeholders[token] = body
    return f"```{lang}\n{token}\n```"

masked = CODE_BLOCK_PATTERN.sub(_mask_closed, raw_cp2)
print("MASKED:")
print(repr(masked))
cleaned = strip_think_tags_v2(masked)
print("CLEANED:")
print(repr(cleaned))
