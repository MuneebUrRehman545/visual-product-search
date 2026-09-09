import logging
import os
import time
from typing import Any, Optional

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Raised when LLM text generation fails after retries."""

    pass


class LLMClient:
    """Provider-agnostic wrapper for LLM generation.

    Uses Google Gemini API as the underlying LLM provider.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        retry_delay: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        self.retry_delay = retry_delay

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
    ) -> str:
        """Generate text or structured output using the LLM given a system prompt and user message.

        Retries once if the initial call fails or times out.
        Raises LLMClientError if generation fails on both attempts.
        """
        if not self.api_key:
            raise LLMClientError("GEMINI_API_KEY is not configured in environment or passed to client.")

        def _call_api() -> str:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt if system_prompt else None,
            )
            config = None
            if response_mime_type or response_schema:
                config_kwargs = {}
                if response_mime_type:
                    config_kwargs["response_mime_type"] = response_mime_type
                if response_schema is not None:
                    config_kwargs["response_schema"] = response_schema
                config = genai.GenerationConfig(**config_kwargs)

            if config is not None:
                response = model.generate_content(user_message, generation_config=config)
            else:
                response = model.generate_content(user_message)

            if not response or not hasattr(response, "text") or response.text is None or not response.text.strip():
                raise RuntimeError("LLM API returned an empty or invalid response.")
            return response.text.strip()

        try:
            return _call_api()
        except Exception as first_err:
            logger.warning(f"LLM API call attempt 1 failed: {first_err}. Retrying in {self.retry_delay}s...")
            if self.retry_delay > 0:
                time.sleep(self.retry_delay)
            try:
                return _call_api()
            except Exception as second_err:
                logger.error(f"LLM API call attempt 2 failed: {second_err}")
                raise LLMClientError(
                    f"LLM text generation failed after retry: {second_err}"
                ) from second_err

    def generate_json(
        self,
        system_prompt: str,
        user_message: str,
        response_schema: Optional[Any] = None,
    ) -> str:
        """Generate structured JSON output using Gemini's JSON mode."""
        return self.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            response_mime_type="application/json",
            response_schema=response_schema,
        )

    def decide_tool_call(
        self,
        step_description: str,
        tools_list: list[dict[str, Any]],
        system_prompt: Optional[str] = None,
        context_summary: Optional[str] = None,
        reformulation_hint: Optional[str] = None,
        intended_tool: Optional[str] = None,
    ) -> tuple[str, dict]:
        """Asks LLM via Gemini native tool-calling which registered tool and arguments
        best satisfy step_description.

        Returns tuple of (tool_name, tool_args).
        """
        import json

        if not self.api_key:
            raise LLMClientError("GEMINI_API_KEY is not configured in environment or passed to client.")

        default_system_prompt = (
            "You are an AI research agent execution engine. Your job is to select the single best tool "
            "and provide exact input arguments to execute the requested step description."
        )
        sys_prompt = system_prompt or default_system_prompt
        user_message = f"Step to execute: {step_description}\n"
        if intended_tool and intended_tool != "none":
            user_message += f"Planned Intended Tool: {intended_tool}\n"
        user_message += "\n"
        if context_summary and context_summary.strip():
            user_message += f"Prior Findings & Context:\n{context_summary.strip()}\n\n"
        if reformulation_hint and reformulation_hint.strip():
            user_message += f"Correction / Retry Guidance:\n{reformulation_hint.strip()}\n\n"

        if intended_tool == "calculator" or any(w in step_description.lower() for w in ("calculate", "compute", "percentage difference", "ratio", "average")):
            user_message += (
                "IMPORTANT: If this step involves calculation, arithmetic, averaging, or computing a formula/percentage, "
                "extract the numeric values from the Prior Findings above and call the 'calculator' tool with a clean "
                "mathematical expression (e.g., expression='(4.44 - 5.05) / 5.05 * 100' or '11140 * 0.15'). Do not call web_search.\n\n"
            )
        user_message += "Select and call the appropriate tool with arguments that best satisfy this step."

        def _call_api() -> tuple[str, dict]:
            genai.configure(api_key=self.api_key)

            declarations = []
            for t in tools_list:
                param_schema = t.get("parameters") or t.get("input_schema") or {}
                fd = genai.types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=param_schema,
                )
                declarations.append(fd)

            gemini_tools = [genai.types.Tool(function_declarations=declarations)] if declarations else None

            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=sys_prompt,
                tools=gemini_tools,
            )

            response = model.generate_content(user_message)

            if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                        tool_name = part.function_call.name
                        tool_args = dict(part.function_call.args) if part.function_call.args else {}
                        return tool_name, tool_args

            if response and hasattr(response, "text") and response.text:
                text = response.text.strip()
                try:
                    clean_text = text
                    if "```" in clean_text:
                        lines = clean_text.splitlines()
                        lines = [l for l in lines if not l.strip().startswith("```")]
                        clean_text = "\n".join(lines).strip()
                    data = json.loads(clean_text)
                    if isinstance(data, dict):
                        tool_name = data.get("tool_name") or data.get("name") or data.get("tool")
                        tool_args = data.get("args") or data.get("input_args") or data.get("arguments") or {}
                        if tool_name:
                            return str(tool_name), dict(tool_args)
                except Exception:
                    pass

            raise RuntimeError("LLM response did not contain a valid function_call.")

        try:
            return _call_api()
        except Exception as first_err:
            logger.warning(f"decide_tool_call attempt 1 failed: {first_err}. Retrying in {self.retry_delay}s...")
            if self.retry_delay > 0:
                time.sleep(self.retry_delay)
            try:
                return _call_api()
            except Exception as second_err:
                logger.error(f"decide_tool_call attempt 2 failed: {second_err}")
                raise LLMClientError(f"Tool selection failed after retry: {second_err}") from second_err


