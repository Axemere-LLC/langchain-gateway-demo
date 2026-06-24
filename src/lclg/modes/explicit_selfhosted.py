"""Explicit + Self-Hosted / Free Gateway mode.

Same ChatAiGateway code as explicit-managed; only the gateway URL differs.
No API key required — POST /v1/actions:execute has no auth on self-hosted.
Gateway: http://localhost:7080 (set AXEMERE_GATEWAY_URL to override)
"""

from __future__ import annotations

from axemere.gateway.langchain import ChatAiGateway

from lclg.config import LCLGConfig


# [AXEMERE] Explicit + Self-Hosted — identical code to managed, different URL
# The gateway URL is the only change between managed and self-hosted modes.
# No API key is required for POST /v1/actions:execute on a self-hosted or Free
# Gateway instance. The gateway applies policy from its local config instead of
# Axemere cloud.
#
# This file and explicit_managed.py are nearly identical — see the comment in
# explicit_managed.py for why we keep them separate.
#
# Alternatives:
#   A) explicit-managed — point AXEMERE_GATEWAY_URL at us.gw.axemere.ai and add
#      AXEMERE_GATEWAY_TOKEN. Axemere manages infra, credentials, and the policy engine.
# Docs: https://axemere.ai/docs/guides/it-setup/docker
def build_explicit_selfhosted(
    cfg: LCLGConfig,
    *,
    provider: str,
    model: str,
    workload_id: str,
    labels: dict[str, str] | None = None,
    max_tokens: int = 1024,
) -> ChatAiGateway:
    """Return a ChatAiGateway instance configured for the self-hosted / Free Gateway."""
    return ChatAiGateway(
        provider=provider,
        model=model,
        config=cfg.gateway,
        workload_id=workload_id,
        labels=labels,
        max_tokens=max_tokens,
    )
