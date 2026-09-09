import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from agent.llm_client import LLMClient, LLMClientError


def test_llm_client_successful_call():
    with patch("google.generativeai.GenerativeModel") as mock_model_class:
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is a successful LLM research response."
        mock_model_instance.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model_instance

        client = LLMClient(api_key="test-key", model_name="gemini-flash-latest", retry_delay=0.001)
        result = client.generate("System prompt", "User goal message")

        assert result == "This is a successful LLM research response."
        mock_model_class.assert_called_once_with(
            model_name="gemini-flash-latest",
            system_instruction="System prompt",
        )
        mock_model_instance.generate_content.assert_called_once_with("User goal message")


def test_llm_client_simulated_timeout_triggers_one_retry():
    with patch("google.generativeai.GenerativeModel") as mock_model_class:
        mock_model_instance = MagicMock()
        mock_success_response = MagicMock()
        mock_success_response.text = "Response text after retry."

        # First call raises TimeoutError, second call succeeds
        mock_model_instance.generate_content.side_effect = [
            TimeoutError("API Call Timed Out"),
            mock_success_response,
        ]
        mock_model_class.return_value = mock_model_instance

        client = LLMClient(api_key="test-key", retry_delay=0.001)
        result = client.generate("System prompt", "User goal message")

        assert result == "Response text after retry."
        assert mock_model_instance.generate_content.call_count == 2


def test_llm_client_fails_twice_raises_custom_exception():
    with patch("google.generativeai.GenerativeModel") as mock_model_class:
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.side_effect = [
            Exception("First API Error"),
            Exception("Second API Error"),
        ]
        mock_model_class.return_value = mock_model_instance

        client = LLMClient(api_key="test-key", retry_delay=0.001)

        with pytest.raises(LLMClientError) as exc_info:
            client.generate("System prompt", "User goal message")

        assert "failed after retry" in str(exc_info.value).lower() or "second api error" in str(exc_info.value).lower()
        assert mock_model_instance.generate_content.call_count == 2


def test_llm_client_missing_api_key_raises_error():
    client = LLMClient(api_key="", retry_delay=0.001)
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        client.api_key = None
        with pytest.raises(LLMClientError) as exc_info:
            client.generate("System prompt", "User goal message")
        assert "GEMINI_API_KEY is not configured" in str(exc_info.value)


def test_llm_client_generate_json_passes_structured_config():
    with patch("google.generativeai.GenerativeModel") as mock_model_class:
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"steps": []}'
        mock_model_instance.generate_content.return_value = mock_response
        mock_model_class.return_value = mock_model_instance

        client = LLMClient(api_key="test-key", retry_delay=0.001)
        result = client.generate_json("Planning prompt", "Research goal")

        assert result == '{"steps": []}'
        mock_model_instance.generate_content.assert_called_once()
        call_args, call_kwargs = mock_model_instance.generate_content.call_args
        assert call_args[0] == "Research goal"
        assert "generation_config" in call_kwargs
        assert call_kwargs["generation_config"].response_mime_type == "application/json"

