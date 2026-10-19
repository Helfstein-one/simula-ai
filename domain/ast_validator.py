"""domain/ast_validator.py - In-memory two-stage AST validator for high-assertiveness code verification."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ASTValidationReport:
    """Detailed result of static AST analysis."""
    is_valid: bool
    error_message: Optional[str] = None
    defined_functions: List[str] = None
    imported_modules: List[str] = None
    has_generator: bool = False
    has_tests: bool = False
    security_violations: List[str] = None


class DomainASTValidator:
    """Performs strict two-stage in-memory validation of generated Python code."""

    FORBIDDEN_FUNCTIONS = {"eval", "exec", "__import__"}
    FORBIDDEN_CALLS = {"os.system", "subprocess.Popen", "subprocess.call"}

    @classmethod
    def validate_syntax(cls, code: str) -> Tuple[bool, Optional[str]]:
        """Stage 1: Pure syntax parsing via Python AST."""
        if not code or not code.strip():
            return False, "Code block is empty or contains no Python instructions."

        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        except Exception as e:
            return False, f"AST Parse Error: {str(e)}"

    @classmethod
    def analyze_structure(cls, code: str) -> ASTValidationReport:
        """Stage 2: Semantic and structural verification against Simula-AI contracts."""
        valid, syntax_err = cls.validate_syntax(code)
        if not valid:
            return ASTValidationReport(
                is_valid=False,
                error_message=syntax_err,
                defined_functions=[],
                imported_modules=[],
                has_generator=False,
                has_tests=False,
                security_violations=[],
            )

        tree = ast.parse(code)
        functions: List[str] = []
        imports: List[str] = []
        violations: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, ast.Call):
                # Security check for forbidden calls
                if isinstance(node.func, ast.Name) and node.func.id in cls.FORBIDDEN_FUNCTIONS:
                    violations.append(f"Forbidden built-in call: {node.func.id}()")
                elif isinstance(node.func, ast.Attribute):
                    full_name = f"{getattr(node.func.value, 'id', '')}.{node.func.attr}"
                    if full_name in cls.FORBIDDEN_CALLS:
                        violations.append(f"Forbidden system call: {full_name}()")

        has_generator = "generate_mock_data" in functions
        has_tests = any(f.startswith("test_") for f in functions)

        err_msgs = []
        if violations:
            err_msgs.append(f"Security constraint violated: {', '.join(violations)}")
        if not has_generator:
            err_msgs.append("Missing mandatory function: `generate_mock_data(rows: int)`")
        if not has_tests:
            err_msgs.append("Missing mandatory Pytest suite: at least one `test_*()` function must be defined")

        is_structurally_valid = len(err_msgs) == 0

        return ASTValidationReport(
            is_valid=is_structurally_valid,
            error_message="; ".join(err_msgs) if err_msgs else None,
            defined_functions=functions,
            imported_modules=imports,
            has_generator=has_generator,
            has_tests=has_tests,
            security_violations=violations,
        )
