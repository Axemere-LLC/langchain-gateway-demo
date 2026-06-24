"""Proxy + Self-Hosted / Free Gateway mode.

Same proxy pattern as proxy-managed; gateway URL points to the local instance.
No API key required.
Gateway: http://localhost:7080 (set AXEMERE_GATEWAY_URL to override)
"""

from __future__ import annotations

from copy import copy

import httpx
from axemere.gateway.langchain import (
    ChatAiGateway,
    ai_gateway_anthropic_client,
    ai_gateway_openai_client,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from lclg.config import LCLGConfig
from lclg.proxy_metering import inject_openai_hook, record_capture_hook


# [AXEMERE] Proxy + Self-Hosted — proxy pattern without a managed account
# Combines the migration-friendly proxy interface with a locally-run gateway.
# Useful for development, testing, or air-gapped environments where no cloud
# connection is available. The gateway holds provider credentials in its local
# configuration; the client code is unchanged from proxy-managed.
# Note: Mistral falls back to ChatAiGateway explicit mode — see inline comment.
# Docs: https://axemere.ai/docs/guides/it-setup/docker
def build_proxy_selfhosted(
    cfg: LCLGConfig,
    *,
    provider: str,
    model: str,
    workload_id: str,
    labels: dict[str, str] | None = None,
    max_tokens: int = 1024,
) -> BaseChatModel:
    """Return a provider-specific LangChain model routed through the local gateway.

    Mistral and Gemini fall back to ChatAiGateway explicit mode. See inline comment.
    """
    agent_cfg = copy(cfg.gateway)
    agent_cfg.workload_id = workload_id

    if provider == "openai":
        hook_client = httpx.Client()
        inject_openai_hook(hook_client)
        openai_native = ai_gateway_openai_client(agent_cfg, http_client=hook_client)
        return ChatOpenAI(
            model=model,
            max_tokens=max_tokens,
            openai_api_client=openai_native,
        )

    if provider == "anthropic":
        hook_client = httpx.Client()
        hook_client.event_hooks["response"].append(record_capture_hook)
        anthropic_native = ai_gateway_anthropic_client(agent_cfg, http_client=hook_client)
        return ChatAnthropic(  # type: ignore[return-value]
            model=model,
            max_tokens=max_tokens,
            anthropic_client=anthropic_native,
        )

    # [AXEMERE] Mistral and Gemini fall back to explicit mode in proxy-selfhosted
    # ChatMistralAI always sends Authorization: Bearer {api_key}. On a self-hosted
    # gateway, this header is treated as a passthrough credential for Mistral and
    # forwarded to api.mistral.ai — where an Axemere placeholder key is invalid
    # and causes 401. The explicit /v1/actions:execute path handles credential
    # injection correctly and does not have this header forwarding issue.
    # This limitation does not affect proxy-managed mode, where the managed gateway
    # authenticates the Authorization header and replaces it before forwarding.
    # Gemini fallback — see proxy_managed.py for the explanation.
    # Docs: https://axemere.ai/docs/guides/developer-integration
    return ChatAiGateway(
        provider=provider,
        model=model,
        config=cfg.gateway,
        workload_id=workload_id,
        labels=labels,
        max_tokens=max_tokens,
    )
