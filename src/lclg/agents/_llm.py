"""Internal helper: build a governed LLM for any mode and provider."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from lclg.config import LCLGConfig
from lclg.modes import (
    build_explicit_managed,
    build_explicit_selfhosted,
    build_proxy_managed,
    build_proxy_selfhosted,
)

_BUILDERS = {
    "explicit-managed": build_explicit_managed,
    "explicit-selfhosted": build_explicit_selfhosted,
    "proxy-managed": build_proxy_managed,
    "proxy-selfhosted": build_proxy_selfhosted,
}


def build_llm(
    cfg: LCLGConfig,
    *,
    provider: str,
    model: str,
    workload_id: str,
    labels: dict[str, str] | None = None,
    # [AXEMERE] max_tokens: SDK default is 256 (intentionally conservative to avoid
    # runaway cost on truncated or repeated outputs). This helper defaults to 1024 as
    # a safer floor for most agents. Agents with heavier output (reporter) or lighter
    # output (planner) should pass their own value explicitly — see each agent file.
    max_tokens: int = 1024,
) -> BaseChatModel:
    """Return a mode-appropriate LangChain chat model for the given provider.

    Selects the builder for ``cfg.mode`` and merges the pipeline ``run_id`` into
    ``labels`` so every gateway record from this run can be filtered together.
    """
    # [AXEMERE] run_id label — cross-agent run filtering in the console
    # run_id is generated once per pipeline invocation and set on LCLGConfig by
    # run_pipeline(). Merging it here means all five agents' gateway records share
    # the same run_id label without any agent needing to pass it explicitly.
    # Filter in the Axemere console: label:run_id=<value>.
    # Alternatives:
    #   A) Pass run_id explicitly to each agent — more verbose; easy to forget.
    #   B) Use a custom workload per run — workloads must be pre-registered;
    #      dynamic workload creation requires the admin API.
    # Docs: https://axemere.ai/docs/attribution
    effective_labels: dict[str, str] = dict(labels) if labels else {}
    if cfg.run_id:
        effective_labels["run_id"] = cfg.run_id

    builder = _BUILDERS[cfg.mode]
    return builder(
        cfg,
        provider=provider,
        model=model,
        workload_id=workload_id,
        labels=effective_labels,
        max_tokens=max_tokens,
    )
