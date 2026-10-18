import re

CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*?)```",
    flags=re.DOTALL,
)
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*)$",
    flags=re.DOTALL,
)

def find_all_code_blocks(text: str):
    blocks = []
    for m in CODE_BLOCK_PATTERN.finditer(text):
        blocks.append({
            "start": m.start(),
            "end": m.end(),
            "lang": m.group(1),
            "body": m.group(2),
            "closed": True,
        })
    last_end = blocks[-1]["end"] if blocks else 0
    remaining = text[last_end:]
    unclosed_m = UNCLOSED_CODE_BLOCK_PATTERN.search(remaining)
    if unclosed_m:
        start = last_end + unclosed_m.start()
        end = len(text)
        blocks.append({
            "start": start,
            "end": end,
            "lang": unclosed_m.group(1),
            "body": unclosed_m.group(2),
            "closed": False,
        })
    return blocks

# Test cases
cases = [
    ("Closed python block", "```python\ndef f(): pass\n```"),
    ("Closed bash + unclosed python", "```bash\npytest\n```\n```python\ndef g(): pass\n"),
    ("Unclosed python only", "```python\ndef h(): pass\n"),
    ("No blocks", "def i(): pass"),
    ("Multiple closed", "```bash\nls\n```\n```python\n1\n```\n```sql\n2\n```"),
]

for name, t in cases:
    res = find_all_code_blocks(t)
    print(f"=== {name} ===")
    for b in res:
        print(f"  lang={b['lang']}, closed={b['closed']}, body={repr(b['body'])}")
