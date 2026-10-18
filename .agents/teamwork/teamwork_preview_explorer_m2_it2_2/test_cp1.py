import re

INNER_THINK_REGEX = re.compile(
    r"<think(?:\s+[^>]*)?>((?:(?!<think\b).)*?)</think\s*>",
    flags=re.DOTALL | re.IGNORECASE,
)

raw_cp1 = "<think>outer_1 <think>inner</think> outer_2</think>\n```python\nimport pytest\ndef test_ok(): pass\n```"

prev = None
cleaned = raw_cp1
step = 0
while prev != cleaned:
    prev = cleaned
    step += 1
    cleaned = INNER_THINK_REGEX.sub("", cleaned)
    print(f"Pass {step}:", repr(cleaned))

print("Final:", repr(cleaned))
