"""Proxy + Managed Gateway mode.

Standard LangChain provider classes route through the gateway proxy.
Attribution is injected as X-MVGC-* headers by the proxy helper functions.
Auth: Bearer axemere_k_... (passed in gateway_token, embedded in proxy URL and headers)
Gateway: https://us.gw.axemere.ai
"""

from __future__ import annotations

from copy import copy

import httpx
from axemere.gateway import PLACEHOLDER_API_KEY
from axemere.gateway.langchain import (
    ChatAiGateway,
    ai_gateway_anthropic_client,
    ai_gateway_openai_client,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI

from lclg.config import LCLGConfig
from lclg.proxy_metering import inject_mistral_hook, inject_openai_hook, record_capture_hook


# [AXEMERE] Proxy + Managed — minimal code change for existing LangChain apps
# Standard LangChain provider classes (ChatOpenAI, ChatAnthropic, ChatMistralAI)
# route through the gateway. The ai_gateway_*_client() helpers return native SDK
# client objects pre-configured with the correct base_url and X-MVGC-* attribution
# headers — no other changes to agent code required.
# Best for: migrating an existing multi-agent app to the gateway one agent at a time.
# Note: Gemini is not available in proxy mode — see ChatAiGateway explicit mode.
# Alternatives:
#   A) explicit-managed — use ChatAiGateway for first-class attribution in the body.
#      More observable and supports all providers including Gemini.
# Docs: https://axemere.ai/docs/guides/developer-integration
def build_proxy_managed(
    cfg: LCLGConfig,
    *,
    provider: str,
    model: str,
    workload_id: str,
    labels: dict[str, str] | None = None,
    max_tokens: int = 1024,
) -> BaseChatModel:
    """Return a provider-specific LangChain model routed through the managed gateway.

    Gemini is not supported in proxy mode; falls back to ChatAiGateway explicit mode.
    """
    # Inject per-agent workload into the config for the proxy headers.
    # We create a shallow override rather than modifying the shared cfg.gateway.
    agent_cfg = copy(cfg.gateway)
    agent_cfg.workload_id = workload_id

    if provider == "openai":
        # [AXEMERE] Proxy mode record-ID capture — OpenAI
        # We create the httpx.Client ourselves so we can inject the response hook
        # before passing it to ai_gateway_openai_client(). The helper accepts any
        # openai.OpenAI kwargs via **kwargs and forwards them — including http_client.
        # inject_openai_hook() registers record_capture_hook, which stores the gateway's
        # X-Mvgc-Record-Id response header in thread-local storage after each call.
        # _MeteringCallback reads it via pop_record_id() in on_llm_end.
        # Docs: https://axemere.ai/docs/guides/developer-integration
        hook_client = httpx.Client()
        inject_openai_hook(hook_client)
        openai_native = ai_gateway_openai_client(agent_cfg, http_client=hook_client)
        return ChatOpenAI(
            model=model,
            max_tokens=max_tokens,
            openai_api_client=openai_native,
        )

    if provider == "anthropic":
        # [AXEMERE] Proxy mode record-ID capture — Anthropic
        # Same pattern as OpenAI: create a hooked httpx.Client first, then pass it
        # to ai_gateway_anthropic_client() via **kwargs. The helper builds an
        # anthropic.Anthropic instance with our hook already attached, which we
        # pass directly to ChatAnthropic(anthropic_client=...).
        # This replaces the old inject_anthropic_hook() workaround that navigated
        # langchain-anthropic's @cached_property chain after construction.
        # Docs: https://axemere.ai/docs/guides/developer-integration
        hook_client = httpx.Client()
        hook_client.event_hooks["response"].append(record_capture_hook)
        anthropic_native = ai_gateway_anthropic_client(agent_cfg, http_client=hook_client)
        return ChatAnthropic(  # type: ignore[return-value]
            model=model,
            max_tokens=max_tokens,
            anthropic_client=anthropic_native,
        )

    if provider == "mistral":
        # [AXEMERE] Mistral proxy URL path — attribution without custom headers
        # ChatMistralAI builds its own httpx.Client and ignores default_headers,
        # so we can't inject X-MVGC-* attribution via headers. Instead we use
        # AiGatewayConfig.proxy_url() to embed the token, workload_id, and
        # project_id in the proxy URL path, which the gateway parses before forwarding:
        #   /proxy/mistral/k/{token}/w/{wid}/p/{pid}/v1/chat/completions
        # ChatMistralAI posts to /chat/completions; we append /v1 to the endpoint
        # so the final path after the gateway strips its prefix is /v1/chat/completions.
        # Docs: https://axemere.ai/docs/guides/developer-integration
        mistral_endpoint = agent_cfg.proxy_url("mistral").rstrip("/") + "/v1"
        cm = ChatMistralAI(  # type: ignore[return-value]
            model=model,
            max_tokens=max_tokens,
            endpoint=mistral_endpoint,
            api_key=agent_cfg.gateway_token or PLACEHOLDER_API_KEY,  # type: ignore[arg-type]
        )
        # [AXEMERE] Proxy mode record-ID capture — Mistral
        # ChatMistralAI.client is a mistralai.Client subclassing httpx.Client directly.
        inject_mistral_hook(cm)
        return cm

    # [AXEMERE] Gemini fallback to explicit mode in proxy configuration
    # The Gemini connector uses the native generateContent API format, which
    # differs from the OpenAI chat completions format that proxy mode sends.
    # Rather than requiring a format translation layer in the gateway, we fall
    # back to ChatAiGateway explicit mode for Gemini regardless of LCLG_MODE.
    # The output and attribution are identical to other providers.
    # Docs: https://axemere.ai/docs/guides/developer-integration
    return ChatAiGateway(
        provider=provider,
        model=model,
        config=cfg.gateway,
        workload_id=workload_id,
        labels=labels,
        max_tokens=max_tokens,
    )
