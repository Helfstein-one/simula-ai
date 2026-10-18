"""core/code_parser.py - Regex cleaning, fence extraction, and AST syntax validation."""

from __future__ import annotations

import ast
import re

# Regex for stripping reasoning tags (handles think, scratchpad, reasoning, thought)
THINK_TAG_REGEX = re.compile(
    r"<(think|scratchpad|reasoning|thought)(?:\s+[^>]*)?>.*?</\1\s*>",
    flags=re.DOTALL | re.IGNORECASE,
)
UNCLOSED_THINK_REGEX = re.compile(
    r"<(think|scratchpad|reasoning|thought)(?:\s+[^>]*)?>.*?(?=```)",
    flags=re.DOTALL | re.IGNORECASE,
)
UNCLOSED_THINK_NO_FENCE_REGEX = re.compile(
    r"<(think|scratchpad|reasoning|thought)(?:\s+[^>]*)?>.*$",
    flags=re.DOTALL | re.IGNORECASE,
)

# Regex for extracting fenced code blocks
CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*?)```",
    flags=re.DOTALL,
)
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(
    r"```([a-zA-Z0-9_\-\.\+]*)\s*\n(.*)$",
    flags=re.DOTALL,
)

NON_PYTHON_LANGUAGES = {
    "bash",
    "sh",
    "zsh",
    "shell",
    "yaml",
    "yml",
    "json",
    "sql",
    "html",
    "xml",
    "css",
    "markdown",
    "md",
    "text",
    "txt",
    "diff",
}


class CodeParser:
    """Extracts, cleans, and validates executable Python code from LLM outputs."""

    @staticmethod
    def strip_think_tags(text: str) -> str:
        """Strip <think>...</think> tags, including unclosed tags using lookaheads."""
        if not text:
            return ""

        # Step 1: Strip standard closed think tags
        cleaned = THINK_TAG_REGEX.sub("", text)

        # Step 2: Handle unclosed reasoning tag
        lower_cleaned = cleaned.lower()
        if any(tag in lower_cleaned for tag in ("<think", "<scratchpad", "<reasoning", "<thought")):
            if "```" in cleaned:
                cleaned = UNCLOSED_THINK_REGEX.sub("", cleaned)
            else:
                cleaned = UNCLOSED_THINK_NO_FENCE_REGEX.sub("", cleaned)

        return cleaned.strip()

    @classmethod
    def extract_python_code(cls, response_text: str) -> str:
        """Strip reasoning tags and extract the primary executable Python code block."""
        cleaned_text = cls.strip_think_tags(response_text)

        # Match closed code blocks
        matches = CODE_BLOCK_PATTERN.findall(cleaned_text)

        candidates: list[str] = []
        if matches:
            for lang, body in matches:
                lang_clean = lang.strip().lower()
                body_clean = body.strip()
                if not body_clean:
                    continue
                # Exclude explicit non-python blocks if alternatives exist
                if lang_clean in NON_PYTHON_LANGUAGES and len(matches) > 1:
                    continue
                candidates.append(body_clean)

        # Fallback to unclosed code block if truncated
        if not candidates:
            unclosed_matches = UNCLOSED_CODE_BLOCK_PATTERN.findall(cleaned_text)
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

    @staticmethod
    def validate_syntax(code: str) -> tuple[bool, str | None]:
        """Verify code syntax using ast.parse without executing it."""
        if not code or not code.strip():
            return False, "Code is empty"

        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        except (ValueError, TypeError) as e:
            return False, f"AST verification failed: {e!s}"
