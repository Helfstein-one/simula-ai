import re

INNER_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>((?:(?!<think\b).)*?)</think\s*>",
    flags=re.DOTALL | re.IGNORECASE,
)

raw_cp2 = """<think>thought 1
<think>thought 1b</think>
```python
def test_bad_draft(): pass
```
</think>
```python
def test_real(): pass
```"""

prev = None
cleaned = raw_cp2
step = 0
while prev != cleaned:
    prev = cleaned
    step += 1
    cleaned = INNER_THINK_REGEX.sub("", cleaned)
    print(f"Pass {step}:", repr(cleaned))

print("Final:", repr(cleaned))
