import pytest
from agent.tools import default_registry
from agent.tools.base import ToolResult
from agent.tools.calculator_tool import CalculatorTool


def test_calculator_tool_registered():
    """Verify CalculatorTool is registered in default_registry under name 'calculator'."""
    tool = default_registry.get_tool("calculator")
    assert tool is not None
    assert isinstance(tool, CalculatorTool)
    assert tool.name == "calculator"


def test_normal_calculation_succeeds():
    """Verify normal arithmetic calculations return success=True and correct numerical results."""
    tool = CalculatorTool()

    # Simple division
    result1 = tool.execute({"expression": "1500000 / 3"})
    assert isinstance(result1, ToolResult)
    assert result1.success is True
    assert result1.data == {"result": 500000.0}
    assert result1.error_message is None

    # Complex expression with decimals and parentheses
    result2 = tool.execute({"expression": "(45.2 - 38.9) / 38.9 * 100"})
    assert isinstance(result2, ToolResult)
    assert result2.success is True
    assert "result" in result2.data
    assert pytest.approx(result2.data["result"], rel=1e-5) == 16.19537275064267
    assert result2.error_message is None

    # Exponents and modulo
    result3 = tool.execute({"expression": "2^3 + 5 % 3"})
    assert result3.success is True
    assert result3.data == {"result": 10}

    # Negative numbers and unary operators
    result4 = tool.execute({"expression": "-15 + (+5 * 2)"})
    assert result4.success is True
    assert result4.data == {"result": -5}


def test_malformed_expression_fails_gracefully():
    """Verify malformed or incomplete expressions fail gracefully with clear error message."""
    tool = CalculatorTool()

    # Incomplete expression
    result1 = tool.execute({"expression": "5 + "})
    assert isinstance(result1, ToolResult)
    assert result1.success is False
    assert result1.error_message is not None
    assert "Malformed" in result1.error_message or "incomplete" in result1.error_message

    # Unbalanced parentheses
    result2 = tool.execute({"expression": "(45.2 - 38.9"})
    assert result2.success is False
    assert result2.error_message is not None
    assert "Malformed" in result2.error_message or "incomplete" in result2.error_message

    # Empty expression string
    result3 = tool.execute({"expression": "   "})
    assert result3.success is False
    assert result3.error_message is not None
    assert "Malformed" in result3.error_message or "incomplete" in result3.error_message


def test_division_by_zero_fails_gracefully():
    """Verify division by zero fails gracefully with a distinct error message."""
    tool = CalculatorTool()

    result1 = tool.execute({"expression": "10 / 0"})
    assert isinstance(result1, ToolResult)
    assert result1.success is False
    assert result1.error_message is not None
    assert "Division by zero" in result1.error_message

    result2 = tool.execute({"expression": "5 % 0"})
    assert result2.success is False
    assert result2.error_message is not None
    assert "Division by zero" in result2.error_message

    result3 = tool.execute({"expression": "100 / (5 - 5)"})
    assert result3.success is False
    assert result3.error_message is not None
    assert "Division by zero" in result3.error_message


def test_disallowed_non_math_content_rejected():
    """Verify attempts to sneak in non-math content (imports, functions, variables) are rejected as unsafe."""
    tool = CalculatorTool()

    # Code injection attempts
    result1 = tool.execute({"expression": "__import__('os').system('ls')"})
    assert isinstance(result1, ToolResult)
    assert result1.success is False
    assert result1.error_message is not None
    assert "disallowed" in result1.error_message.lower() or "unsafe" in result1.error_message.lower()

    # Variable lookup
    result2 = tool.execute({"expression": "x + 5"})
    assert result2.success is False
    assert result2.error_message is not None
    assert "disallowed" in result2.error_message.lower() or "unsafe" in result2.error_message.lower()

    # Built-in function calls
    result3 = tool.execute({"expression": "abs(-5)"})
    assert result3.success is False
    assert result3.error_message is not None
    assert "disallowed" in result3.error_message.lower() or "unsafe" in result3.error_message.lower()

    # String literals
    result4 = tool.execute({"expression": "'hello' + 'world'"})
    assert result4.success is False
    assert result4.error_message is not None
    assert "disallowed" in result4.error_message.lower() or "unsafe" in result4.error_message.lower()


def test_overflow_and_non_finite_number_fails():
    """Verify overflow or non-finite calculation results fail gracefully."""
    tool = CalculatorTool()

    result = tool.execute({"expression": "10 ** 100000"})
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert result.error_message is not None
    assert "finite" in result.error_message.lower() or "overflow" in result.error_message.lower()


def test_invalid_input_arguments():
    """Verify invalid input structures fail gracefully."""
    tool = CalculatorTool()

    result1 = tool.execute("not a dict")
    assert result1.success is False
    assert result1.error_message is not None

    result2 = tool.execute({"wrong_key": "1 + 1"})
    assert result2.success is False
    assert result2.error_message is not None
