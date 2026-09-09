import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent.tools.base import Tool, ToolResult
from agent.tools.file_write_tool import DEFAULT_STORAGE_DIR, get_safe_target_path

logger = logging.getLogger(__name__)


class FileReadTool(Tool):
    """Tool that reads string content from a file inside the run's isolated storage directory."""

    name = "file_read"
    description = (
        "Reads string content from a specified filename in the run's isolated storage directory."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The name of the file to read from (e.g. 'notes.txt').",
            },
        },
        "required": ["filename"],
    }

    def __init__(self, run_id: Optional[str] = None, storage_dir: Optional[Path] = None):
        self.run_id = run_id
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR

    def execute(self, args: dict, run_id: Optional[str] = None) -> ToolResult:
        """Executes reading content from backend/storage/{run_id}/{filename}.

        Returns ToolResult(success=True, data={"content": ...}) on success,
        or a graceful failure ToolResult otherwise.
        """
        try:
            if not isinstance(args, dict):
                return ToolResult(
                    success=False,
                    error_message="Invalid input arguments: expected a dictionary.",
                )

            filename = args.get("filename")
            if filename is None or not isinstance(filename, str):
                return ToolResult(
                    success=False,
                    error_message="Invalid input: 'filename' string is required.",
                )

            effective_run_id = run_id or args.get("run_id") or self.run_id
            target_path, err_msg = get_safe_target_path(
                self.storage_dir, str(effective_run_id) if effective_run_id else "", filename
            )
            if not target_path or err_msg:
                return ToolResult(success=False, error_message=err_msg)

            if not target_path.exists() or not target_path.is_file():
                return ToolResult(
                    success=False,
                    error_message=f"File not found: '{filename}'",
                )

            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()

            return ToolResult(
                success=True,
                data={"content": content},
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Unexpected error in FileReadTool execution: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error_message=f"Failed to read file: {str(e)}",
            )
