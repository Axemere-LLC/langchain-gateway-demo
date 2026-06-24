"""Proxy-mode metering helpers for LCLG.

In proxy mode, LangChain's native providers (ChatOpenAI, ChatAnthropic,
ChatMistralAI) route through the gateway but don't return gateway metering data
in generation_info — only ChatAiGateway does that via the explicit execution path.

This module provides three complementary mechanisms to recover metering data:

1. httpx event hooks — capture X-Mvgc-Record-Id from every gateway response
   header, regardless of whether the call is streaming or not.

2. llm_output fallback — extract token counts from native provider response
   objects (available in on_llm_end for non-streaming invoke calls only;
   streaming returns llm_output=None).

3. Admin API enrichment — when MVGC_ADMIN_TOKEN is set, fetch full metering
   (tokens, cost, model, provider) from GET /v1/records/{id}. This covers
   streaming calls where llm_output is unavailable.

Usage pattern in proxy modes:

    # OpenAI: create a hooked httpx.Client, pass it to ai_gateway_openai_client()
    hook_client = httpx.Client()
    inject_openai_hook(hook_client)
    openai_client = ai_gateway_openai_client(cfg, http_client=hook_client)
    llm = ChatOpenAI(openai_api_client=openai_client, model=model)

    # Anthropic: same pattern — hook client passed into ai_gateway_anthropic_client()
    hook_client = httpx.Client()
    hook_client.event_hooks["response"].append(record_capture_hook)
    anthropic_client = ai_gateway_anthropic_client(cfg, http_client=hook_client)
    llm = ChatAnthropic(anthropic_client=anthropic_client, model=model)

    # Mistral: patch the httpx.Client subclass used by ChatMistralAI
    llm = ChatMistralAI(...)
    inject_mistral_hook(llm)

All hooks write to thread-local storage, which is safe for the parallel
researcher pattern because each ThreadPoolExecutor thread has its own storage
and httpx fires event hooks on the thread that receives the response.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from langchain_mistralai import ChatMistralAI

_thread_local = threading.local()


# ---------------------------------------------------------------------------
# httpx event hook — fires on the thread that receives the HTTP response
# ---------------------------------------------------------------------------


def record_capture_hook(response: httpx.Response) -> None:
    """Store X-Mvgc-Record-Id from a gateway response in thread-local storage.

    Register via inject_*_hook() before the first LLM call.
    """
    rid = response.headers.get("X-Mvgc-Record-Id", "")
    if rid:
        _thread_local.record_id = rid


def pop_record_id() -> str:
    """Return and clear the thread-local gateway record ID, or empty string.

    Call once per on_llm_end invocation. Thread-safe: each thread has its own
    storage, so parallel researcher calls don't interfere with each other.
    """
    rid = getattr(_thread_local, "record_id", "")
    if rid:
        del _thread_local.record_id
    return rid


# ---------------------------------------------------------------------------
# Hook injection helpers
# ---------------------------------------------------------------------------


def inject_openai_hook(http_client: httpx.Client) -> None:
    """Add the record capture hook to an httpx.Client used by ChatOpenAI.

    Create an httpx.Client, call this, then pass it to ai_gateway_openai_client()
    via http_client= kwarg so the hook is already registered before the first call.
    """
    if record_capture_hook not in http_client.event_hooks["response"]:
        http_client.event_hooks["response"].append(record_capture_hook)


def inject_mistral_hook(chat_mistral: ChatMistralAI) -> None:
    """Inject the record capture hook into ChatMistralAI's httpx client.

    ChatMistralAI.client is a mistralai.Client which subclasses httpx.Client
    directly, so event_hooks is directly accessible.
    """
    try:
        if record_capture_hook not in chat_mistral.client.event_hooks["response"]:
            chat_mistral.client.event_hooks["response"].append(record_capture_hook)
    except Exception:
        # Silently degrade: record_id will be empty string; metering falls back
        # to llm_output (tokens only, no cost) for this agent's calls.
        pass


# ---------------------------------------------------------------------------
# Native llm_output token extraction
# ---------------------------------------------------------------------------


def extract_native_metering(
    llm_output: dict[str, Any] | None,
) -> tuple[int, int, str, str]:
    """Extract (tokens_in, tokens_out, model, provider) from a native provider's llm_output.

    Called in _MeteringCallback.on_llm_end when generation_info has no gateway
    metering (i.e. for native proxy-mode providers, not ChatAiGateway).

    ChatOpenAI (non-streaming): llm_output["token_usage"]["prompt_tokens/completion_tokens"]
    ChatAnthropic (non-streaming): llm_output["usage"]["input_tokens/output_tokens"]
    Streaming calls: llm_output=None → returns (0, 0, "", "")
    """
    if not llm_output:
        return 0, 0, "", ""

    model = str(llm_output.get("model_name") or llm_output.get("model") or "")

    # [AXEMERE] OpenAI llm_output format
    if "token_usage" in llm_output:
        usage = llm_output["token_usage"]
        return (
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            model,
            "openai",
        )

    # [AXEMERE] Anthropic llm_output format
    if "usage" in llm_output and "input_tokens" in llm_output.get("usage", {}):
        usage = llm_output["usage"]
        return (
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
            model,
            "anthropic",
        )

    return 0, 0, model, ""


# ---------------------------------------------------------------------------
# Admin API enrichment (self-hosted / Docker gateway only)
# ---------------------------------------------------------------------------


def fetch_record_metering(
    gateway_url: str,
    record_id: str,
    admin_token: str,
) -> dict[str, Any]:
    """Fetch full gateway metering for a record using the admin API.

    Requires MVGC_ADMIN_TOKEN. Covers streaming calls where llm_output=None.
    Useful for self-hosted / Docker gateway where the admin token is available.

    Returns an empty dict on any error so callers can degrade gracefully.

    Response fields used:
        metering.tokens_in, metering.tokens_out, metering.usd_charged,
        connector.connector_id (provider name), model
    """
    try:
        resp = httpx.get(
            f"{gateway_url}/v1/records/{record_id}",
            headers={"MVGC-Admin-Token": admin_token},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        metering = data.get("metering", {})
        return {
            "tokens_in": int(metering.get("tokens_in", 0)),
            "tokens_out": int(metering.get("tokens_out", 0)),
            "usd_charged": str(metering.get("usd_charged", "0.00000")),
            "model": str(data.get("model", "")),
            "provider": str(data.get("connector", {}).get("connector_id", "")),
        }
    except Exception:
        return {}
