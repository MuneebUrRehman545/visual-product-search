import logging
from typing import Any, Dict, List, Optional

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry managing available tools, listing schemas for LLM tool selection,
    and safely dispatching execution with error wrapping.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registers a tool instance into the registry."""
        if not hasattr(tool, "name") or not tool.name:
            raise ValueError("Cannot register a tool without a valid name.")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool in ToolRegistry: {tool.name}")

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(tool_name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Lists all registered tools' name, description, and input_schema,
        formatted for Gemini function-calling / tool-use API.
        """
        tools_list = []
        for tool in self._tools.values():
            tools_list.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
                "input_schema": tool.input_schema,
            })
        return tools_list

    def dispatch(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        run_id: Optional[Any] = None,
    ) -> ToolResult:
        """Dispatches execution to the specified tool with arguments.

        Wraps ANY exception (even unexpected ones raised inside tool.execute)
        in a ToolResult with success=False rather than crashing the caller.
        """
        if args is None:
            args = {}

        tool = self._tools.get(tool_name)
        if not tool:
            msg = f"Tool '{tool_name}' is not registered."
            logger.warning(msg)
            return ToolResult(success=False, data=None, error_message=msg)

        try:
            dispatch_args = dict(args)
            if run_id is not None and "run_id" not in dispatch_args:
                dispatch_args["run_id"] = str(run_id)

            import inspect
            sig = inspect.signature(tool.execute)
            if "run_id" in sig.parameters:
                result = tool.execute(dispatch_args, run_id=str(run_id) if run_id is not None else None)
            else:
                result = tool.execute(dispatch_args)

            if not isinstance(result, ToolResult):
                return ToolResult(success=True, data=result, error_message=None)
            return result
        except Exception as e:
            err_msg = f"Unhandled exception in tool '{tool_name}': {str(e)}"
            logger.error(err_msg, exc_info=True)
            return ToolResult(success=False, data=None, error_message=err_msg)

