from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Represents the standardized result returned by any tool execution."""

    success: bool
    data: Any = None
    error_message: Optional[str] = None


class Tool(ABC):
    """Abstract base class interface for all tools in the framework."""

    name: str = ""
    description: str = ""
    input_schema: dict = {}

    @abstractmethod
    def execute(self, args: dict) -> ToolResult:
        """Executes the tool with the given arguments dictionary and returns a ToolResult."""
        pass
