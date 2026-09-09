import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from agent.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# Base storage directory relative to backend folder
DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage"
MAX_FILE_SIZE_BYTES = 1_048_576  # 1MB limit


def get_safe_target_path(
    storage_dir: Path, run_id: str, filename: str
) -> Tuple[Optional[Path], Optional[str]]:
    """Validates run_id and filename for path safety and returns (target_path, error_message).

    Prevents directory traversal (e.g., '../') and writing/reading outside the run's storage folder.
    """
    if not run_id or not str(run_id).strip():
        return None, "Missing or empty run_id for file operation."

    if not filename or not isinstance(filename, str) or not filename.strip():
        return None, "Invalid filename: filename must be a non-empty string."

    filename_str = filename.strip()

    # Reject explicit directory traversal indicators
    if "../" in filename_str or "..\\" in filename_str or filename_str.startswith(".."):
        return (
            None,
            f"Invalid or unsafe filename: '{filename}'. Directory traversal ('../') is forbidden.",
        )

    run_dir = (storage_dir / str(run_id).strip()).resolve()

    try:
        target_path = (run_dir / filename_str).resolve()
    except Exception as e:
        return None, f"Invalid path construct for filename '{filename}': {str(e)}"

    # Ensure target_path is strictly within run_dir
    try:
        target_path.relative_to(run_dir)
    except ValueError:
        return (
            None,
            f"Invalid or unsafe filename: '{filename}'. Access outside run directory is forbidden.",
        )

    return target_path, None


class FileWriteTool(Tool):
    """Tool that writes string content to a file inside the run's isolated storage directory."""

    name = "file_write"
    description = (
        "Writes string content to a specified filename in the run's isolated storage directory."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "The name of the file to write to (e.g. 'notes.txt').",
            },
            "content": {
                "type": "string",
                "description": "The string content to write into the file.",
            },
        },
        "required": ["filename", "content"],
    }

    def __init__(self, run_id: Optional[str] = None, storage_dir: Optional[Path] = None):
        self.run_id = run_id
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR

    def execute(self, args: dict, run_id: Optional[str] = None) -> ToolResult:
        """Executes writing content to backend/storage/{run_id}/{filename}.

        Returns ToolResult(success=True, data={"filename": ..., "bytes_written": ...}) on success,
        or a graceful failure ToolResult otherwise.
        """
        try:
            if not isinstance(args, dict):
                return ToolResult(
                    success=False,
                    error_message="Invalid input arguments: expected a dictionary.",
                )

            filename = args.get("filename")
            content = args.get("content")

            if filename is None or not isinstance(filename, str):
                return ToolResult(
                    success=False,
                    error_message="Invalid input: 'filename' string is required.",
                )

            if content is None or not isinstance(content, str):
                return ToolResult(
                    success=False,
                    error_message="Invalid input: 'content' string is required.",
                )

            effective_run_id = run_id or args.get("run_id") or self.run_id
            target_path, err_msg = get_safe_target_path(
                self.storage_dir, str(effective_run_id) if effective_run_id else "", filename
            )
            if not target_path or err_msg:
                return ToolResult(success=False, error_message=err_msg)

            content_bytes = content.encode("utf-8")
            if len(content_bytes) > MAX_FILE_SIZE_BYTES:
                return ToolResult(
                    success=False,
                    error_message=(
                        f"Content size ({len(content_bytes)} bytes) exceeds the maximum "
                        f"allowed size of {MAX_FILE_SIZE_BYTES} bytes (1MB)."
                    ),
                )

            # Ensure run directory exists automatically
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                data={
                    "filename": filename,
                    "bytes_written": len(content_bytes),
                },
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Unexpected error in FileWriteTool execution: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error_message=f"Disk write failure: {str(e)}",
            )
