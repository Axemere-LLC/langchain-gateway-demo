"""Tests for proxy-mode metering helpers."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import httpx

from lclg.proxy_metering import (
    extract_native_metering,
    fetch_record_metering,
    inject_mistral_hook,
    inject_openai_hook,
    pop_record_id,
    record_capture_hook,
)

# ---------------------------------------------------------------------------
# Thread-local record ID capture
# ---------------------------------------------------------------------------


class TestRecordCaptureHook:
    def test_captures_record_id(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {"X-Mvgc-Record-Id": "rec_abc123"}
        record_capture_hook(mock_response)
        assert pop_record_id() == "rec_abc123"

    def test_ignores_missing_header(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {}
        record_capture_hook(mock_response)
        assert pop_record_id() == ""

    def test_pop_clears_value(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {"X-Mvgc-Record-Id": "rec_xyz"}
        record_capture_hook(mock_response)
        assert pop_record_id() == "rec_xyz"
        assert pop_record_id() == ""  # cleared after first pop

    def test_thread_local_isolation(self) -> None:
        """Each thread captures its own record ID without cross-thread interference."""
        results: dict[int, str] = {}

        def worker(thread_idx: int, record_id: str) -> None:
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.headers = {"X-Mvgc-Record-Id": record_id}
            record_capture_hook(mock_resp)
            results[thread_idx] = pop_record_id()

        threads = [threading.Thread(target=worker, args=(i, f"rec_thread_{i}")) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(4):
            assert results[i] == f"rec_thread_{i}"


# ---------------------------------------------------------------------------
# Native llm_output token extraction
# ---------------------------------------------------------------------------


class TestExtractNativeMetering:
    def test_none_input(self) -> None:
        assert extract_native_metering(None) == (0, 0, "", "")

    def test_empty_dict(self) -> None:
        assert extract_native_metering({}) == (0, 0, "", "")

    def test_openai_format(self) -> None:
        llm_output = {
            "token_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 45,
                "total_tokens": 165,
            },
            "model_name": "gpt-4o-mini",
        }
        tokens_in, tokens_out, model, provider = extract_native_metering(llm_output)
        assert tokens_in == 120
        assert tokens_out == 45
        assert model == "gpt-4o-mini"
        assert provider == "openai"

    def test_anthropic_format(self) -> None:
        llm_output = {
            "usage": {
                "input_tokens": 88,
                "output_tokens": 312,
                "cache_read_input_tokens": 0,
            },
            "model_name": "claude-haiku-4-5-20251001",
        }
        tokens_in, tokens_out, model, provider = extract_native_metering(llm_output)
        assert tokens_in == 88
        assert tokens_out == 312
        assert model == "claude-haiku-4-5-20251001"
        assert provider == "anthropic"

    def test_anthropic_usage_without_input_tokens_not_matched(self) -> None:
        # "usage" key present but not Anthropic format (no input_tokens)
        llm_output = {"usage": {"foo": 1}, "model_name": "unknown"}
        tokens_in, tokens_out, model, provider = extract_native_metering(llm_output)
        assert tokens_in == 0
        assert tokens_out == 0
        assert provider == ""

    def test_model_name_fallback(self) -> None:
        # Some providers use "model" instead of "model_name"
        llm_output = {
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "gpt-4o",
        }
        _, _, model, _ = extract_native_metering(llm_output)
        assert model == "gpt-4o"

    def test_missing_token_fields_default_to_zero(self) -> None:
        llm_output = {"token_usage": {}, "model_name": "gpt-4o-mini"}
        tokens_in, tokens_out, _, _ = extract_native_metering(llm_output)
        assert tokens_in == 0
        assert tokens_out == 0


# ---------------------------------------------------------------------------
# Hook injection helpers
# ---------------------------------------------------------------------------


class TestInjectOpenAIHook:
    def test_adds_hook_to_client(self) -> None:
        client = httpx.Client()
        inject_openai_hook(client)
        assert record_capture_hook in client.event_hooks["response"]

    def test_does_not_duplicate(self) -> None:
        client = httpx.Client()
        inject_openai_hook(client)
        inject_openai_hook(client)
        assert client.event_hooks["response"].count(record_capture_hook) == 1


class TestAnthropicHookPattern:
    def test_pre_hooked_httpx_client_pattern(self) -> None:
        """Anthropic hook: register record_capture_hook on httpx.Client before client creation."""
        # New pattern: create the httpx.Client ourselves and register the hook directly.
        # ai_gateway_anthropic_client() accepts http_client= via **kwargs, so the hook
        # is attached before anthropic.Anthropic builds any internal connections.
        hook_client = httpx.Client()
        hook_client.event_hooks["response"].append(record_capture_hook)
        assert record_capture_hook in hook_client.event_hooks["response"]

    def test_does_not_duplicate_on_repeated_append(self) -> None:
        """Guard: only one hook registration per client."""
        hook_client = httpx.Client()
        if record_capture_hook not in hook_client.event_hooks["response"]:
            hook_client.event_hooks["response"].append(record_capture_hook)
        if record_capture_hook not in hook_client.event_hooks["response"]:
            hook_client.event_hooks["response"].append(record_capture_hook)
        assert hook_client.event_hooks["response"].count(record_capture_hook) == 1


class TestInjectMistralHook:
    def test_injects_into_client(self) -> None:
        mock_chat = MagicMock()
        mock_httpx = MagicMock(spec=httpx.Client)
        mock_httpx.event_hooks = {"response": []}
        mock_chat.client = mock_httpx

        inject_mistral_hook(mock_chat)

        assert record_capture_hook in mock_httpx.event_hooks["response"]

    def test_does_not_raise_on_error(self) -> None:
        bad_mock = MagicMock()
        bad_mock.client = None
        inject_mistral_hook(bad_mock)  # should not raise


# ---------------------------------------------------------------------------
# Admin API enrichment
# ---------------------------------------------------------------------------


class TestFetchRecordMetering:
    def test_returns_metering_on_success(self) -> None:
        gateway_record = {
            "model": "claude-haiku-4-5-20251001",
            "metering": {
                "tokens_in": 100,
                "tokens_out": 250,
                "usd_charged": "0.00012345",
            },
            "connector": {"connector_id": "anthropic"},
        }

        with patch("lclg.proxy_metering.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = gateway_record
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            result = fetch_record_metering(
                "http://localhost:7080",
                "rec_abc123",
                "admin-token",
            )

        assert result["tokens_in"] == 100
        assert result["tokens_out"] == 250
        assert result["usd_charged"] == "0.00012345"
        assert result["model"] == "claude-haiku-4-5-20251001"
        assert result["provider"] == "anthropic"

    def test_returns_empty_dict_on_error(self) -> None:
        with patch("lclg.proxy_metering.httpx.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("connection refused")
            result = fetch_record_metering(
                "http://localhost:7080",
                "rec_abc123",
                "admin-token",
            )
        assert result == {}

    def test_returns_empty_dict_on_http_error(self) -> None:
        with patch("lclg.proxy_metering.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            mock_get.return_value = mock_resp
            result = fetch_record_metering(
                "http://localhost:7080",
                "rec_abc123",
                "admin-token",
            )
        assert result == {}

    def test_builds_correct_url(self) -> None:
        with patch("lclg.proxy_metering.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"metering": {}, "connector": {}}
            mock_resp.raise_for_status.return_value = None
            mock_get.return_value = mock_resp

            fetch_record_metering(
                "http://localhost:7080",
                "rec_019ef043-abcd",
                "my-admin-token",
            )

            mock_get.assert_called_once_with(
                "http://localhost:7080/v1/records/rec_019ef043-abcd",
                headers={"MVGC-Admin-Token": "my-admin-token"},
                timeout=5.0,
            )
