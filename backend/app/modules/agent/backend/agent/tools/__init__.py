from agent.tools.base import Tool, ToolResult
from agent.tools.calculator_tool import CalculatorTool
from agent.tools.echo_tool import EchoTool
from agent.tools.file_read_tool import FileReadTool
from agent.tools.file_write_tool import FileWriteTool
from agent.tools.registry import ToolRegistry
from agent.tools.web_search_tool import WebSearchTool

# Default global tool registry instance with tools registered at startup
default_registry = ToolRegistry()
default_registry.register(EchoTool())
default_registry.register(WebSearchTool())
default_registry.register(FileWriteTool())
default_registry.register(FileReadTool())
default_registry.register(CalculatorTool())

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "EchoTool",
    "WebSearchTool",
    "FileWriteTool",
    "FileReadTool",
    "CalculatorTool",
    "default_registry",
]


