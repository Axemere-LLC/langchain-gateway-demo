"""Explicit + Managed Gateway mode.

Agents use ChatAiGateway — attribution is first-class in the request body.
Auth: Bearer axemere_k_... (bound server-side to the account).
Gateway: https://us.gw.axemere.ai
"""

from __future__ import annotations

from axemere.gateway.langchain import ChatAiGateway

from lclg.config import LCLGConfig


# [AXEMERE] Explicit + Managed — the recommended starting point
# Every LLM call becomes POST /v1/actions:execute to the Axemere managed gateway.
# Attribution fields (workload_id, project_id, labels) are first-class in the
# request body and visible in the Axemere console immediately.
#
# This file and explicit_selfhosted.py are nearly identical — the only runtime
# difference is the gateway URL (managed vs self-hosted), which comes from
# AXEMERE_GATEWAY_URL via AiGatewayConfig. We keep them as separate files so
# LCLG_MODE is reflected in the module that handles the call, making it easy to
# add mode-specific behaviour (e.g. different retry policies or auth headers)
# later without touching the other mode.
#
# Alternatives:
#   A) proxy-managed — use ChatOpenAI/ChatAnthropic/ChatMistralAI with base_url
#      override; attribution via X-MVGC-* headers. Better for migrating existing code.
#   B) explicit-selfhosted — swap gateway URL; no API key required.
# Docs: https://axemere.ai/docs/guides/developer-integration
def build_explicit_managed(
    cfg: LCLGConfig,
    *,
    provider: str,
    model: str,
    workload_id: str,
    labels: dict[str, str] | None = None,
    max_tokens: int = 1024,
) -> ChatAiGateway:
    """Return a ChatAiGateway instance configured for the managed gateway."""
    return ChatAiGateway(
        provider=provider,
        model=model,
        config=cfg.gateway,
        workload_id=workload_id,
        labels=labels,
        max_tokens=max_tokens,
    )
