from agent.tools.base import Tool, ToolResult


class EchoTool(Tool):
    """Dummy test tool that echoes back input messages.

    Deliberately raises an exception when message is "CRASH_TEST" to verify
    uncaught error handling in the registry.
    """

    name = "echo"
    description = "Echoes back the input message. Used for framework testing."
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message string to echo back.",
            }
        },
        "required": ["message"],
    }

    def execute(self, args: dict) -> ToolResult:
        if not isinstance(args, dict):
            return ToolResult(
                success=False,
                error_message="Arguments must be a dictionary.",
            )

        message = args.get("message", "")
        if message == "CRASH_TEST":
            raise RuntimeError("CRASH_TEST exception triggered in EchoTool")

        return ToolResult(
            success=True,
            data={"echoed": message},
            error_message=None,
        )
