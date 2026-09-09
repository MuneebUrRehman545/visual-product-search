import ast
import logging
import math
from typing import Any, Dict, Union

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class CalculatorTool(Tool):
    """Tool for safely evaluating basic arithmetic expressions without using raw eval()."""

    name = "calculator"
    description = (
        "Safely evaluates basic arithmetic expressions (+, -, *, /, %, exponents, parentheses)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "The arithmetic expression to evaluate (e.g., '1500000 / 3', "
                    "'(45.2 - 38.9) / 38.9 * 100')."
                ),
            }
        },
        "required": ["expression"],
    }

    def execute(self, args: dict) -> ToolResult:
        """Evaluates an arithmetic expression safely.

        Returns ToolResult(success=True, data={"result": <number>}) on success,
        or ToolResult(success=False, error_message=...) on failure.
        Never allows exceptions to escape.
        """
        try:
            if not isinstance(args, dict):
                return ToolResult(
                    success=False,
                    error_message="Invalid input arguments: expected a dictionary.",
                )

            raw_expr = args.get("expression")
            if raw_expr is None or not isinstance(raw_expr, str):
                return ToolResult(
                    success=False,
                    error_message="Invalid input arguments: 'expression' string is required.",
                )

            expr_str = raw_expr.strip()
            if not expr_str:
                return ToolResult(
                    success=False,
                    error_message="Malformed or incomplete expression: expression cannot be empty.",
                )

            # Strip leading '=' or 'calculate ' if present
            if expr_str.startswith("="):
                expr_str = expr_str[1:].strip()
            if expr_str.lower().startswith("calculate "):
                expr_str = expr_str[10:].strip()

            # Remove currency symbols ($ € £ ¥) and trailing %
            for sym in ("$", "€", "£", "¥"):
                expr_str = expr_str.replace(sym, "")
            if expr_str.endswith("%"):
                expr_str = expr_str[:-1].strip()

            # Remove commas inside numbers (e.g. 1,000,000 -> 1000000)
            import re
            expr_str = re.sub(r'(?<=\d),(?=\d)', '', expr_str)

            # Replace '^' with '**' for exponentiation compatibility
            expr_str = expr_str.replace("^", "**")

            # Parse expression into AST safely
            try:
                tree = ast.parse(expr_str, mode="eval")
            except SyntaxError as syn_err:
                return ToolResult(
                    success=False,
                    error_message=(
                        f"Malformed arithmetic expression '{raw_expr}': {str(syn_err)}. "
                        "The calculator tool requires standard Python arithmetic syntax "
                        "(e.g., '(4.44 - 5.05) / 5.05 * 100' or '11140 * 0.15')."
                    ),
                )

            # Validate AST nodes to ensure no disallowed/unsafe content
            if not self._is_safe_ast(tree):
                return ToolResult(
                    success=False,
                    error_message=(
                        f"Expression '{raw_expr}' contains disallowed functions, variables, or syntax. "
                        "Only plain arithmetic numbers and operators (+, -, *, /, %, **) with parentheses are allowed."
                    ),
                )

            # Evaluate AST
            try:
                result_val = self._eval_ast(tree.body)
            except ZeroDivisionError:
                return ToolResult(
                    success=False,
                    error_message="Division by zero.",
                )
            except (OverflowError, ValueError):
                return ToolResult(
                    success=False,
                    error_message="Result is not a finite number.",
                )

            # Validate that the result is a finite number (int or float)
            if isinstance(result_val, (int, float)) and not isinstance(result_val, bool):
                if math.isnan(result_val) or math.isinf(result_val):
                    return ToolResult(
                        success=False,
                        error_message="Result is not a finite number.",
                    )
                return ToolResult(
                    success=True,
                    data={"result": result_val},
                    error_message=None,
                )
            else:
                return ToolResult(
                    success=False,
                    error_message="Expression did not evaluate to a valid number.",
                )

        except Exception as e:
            logger.error(f"Unexpected error in CalculatorTool.execute: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error_message=f"Unexpected error in CalculatorTool: {str(e)}",
            )

    def _is_safe_ast(self, tree: ast.AST) -> bool:
        """Traverses the AST tree to ensure only plain arithmetic nodes exist."""
        allowed_types = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.UAdd,
            ast.USub,
        )
        for node in ast.walk(tree):
            if isinstance(node, allowed_types):
                continue
            elif isinstance(node, ast.Constant):
                if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                    return False
                continue
            else:
                return False
        return True

    def _eval_ast(self, node: ast.AST) -> Union[int, float]:
        """Recursively evaluates a validated arithmetic AST node."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_ast(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            elif isinstance(node.op, ast.USub):
                return -operand
            else:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")
        elif isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            op = node.op

            if isinstance(op, ast.Add):
                return left + right
            elif isinstance(op, ast.Sub):
                return left - right
            elif isinstance(op, ast.Mult):
                return left * right
            elif isinstance(op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                return left / right
            elif isinstance(op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                return left // right
            elif isinstance(op, ast.Mod):
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                return left % right
            elif isinstance(op, ast.Pow):
                if abs(right) > 10000 or (isinstance(left, (int, float)) and abs(left) > 1000000 and right > 100):
                    raise OverflowError("Exponent too large")
                return left ** right
            else:
                raise ValueError(f"Unsupported binary operator: {type(op)}")
        else:
            raise ValueError(f"Unsupported AST node: {type(node)}")
