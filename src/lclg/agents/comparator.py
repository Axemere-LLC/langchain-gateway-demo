"""ComparatorAgent: fan the same prompt to three providers in parallel.

Always uses ChatAiGateway explicit mode regardless of LCLG_MODE — see
docs/gateway-integration.md#gemini-in-proxy-mode for the rationale.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from axemere.gateway.langchain import ChatAiGateway
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableLambda, RunnableParallel

from lclg.config import WORKLOAD_COMPARATOR, LCLGConfig


# [AXEMERE] Gemini thinking workaround
# gemini-2.5-flash uses "thinking tokens" that consume the maxOutputTokens budget
# silently before generating visible output. With max_tokens=1024, ~984 tokens go to
# thinking, leaving only ~40 visible — the response appears cut off. With higher limits
# (4096+), the gateway connector timeout fires before Gemini finishes thinking.
# Workaround: subclass ChatAiGateway and inject thinkingConfig.thinkingBudget=0 into
# the Gemini generationConfig, which disables thinking for this call.
# SDK gap: the Python SDK has no first-class thinkingConfig parameter — this subclass
# can be removed once the SDK exposes it. Track in SDK backlog.
class _ChatAiGatewayNoThinking(ChatAiGateway):
    def _messages_to_gemini(
        self, messages: list[BaseMessage]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
        system_instruction, contents, generation_config = super()._messages_to_gemini(messages)
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        return system_instruction, contents, generation_config


# [AXEMERE] multi-provider comparison via RunnableParallel
# RunnableParallel fans the same prompt to three providers simultaneously.
# All three calls share a single workload_id (wl_lclg_comparator) so the
# combined cost appears as one line in the console, with per-call detail
# available in the Attribution Breakdown via the record_id on each generation.
# Attribution labels distinguish the three providers: {"provider": "openai"} etc.
# Alternatives:
#   A) Sequential calls — simpler but 3x slower; loses the latency comparison.
#   B) Separate workload_id per provider — finer-grained console view but
#      requires three workload registrations instead of one.
# Docs: https://axemere.ai/docs/guides/configuration/workloads
PROVIDERS = [
    {"key": "openai", "provider": "openai", "model": "gpt-4o"},
    {"key": "anthropic", "provider": "anthropic", "model": "claude-sonnet-4-6"},
    {"key": "google", "provider": "google", "model": "gemini-2.5-flash"},
]


@dataclass
class ProviderResult:
    """Single-provider response from the ComparatorAgent fan-out."""

    provider: str
    model: str
    response: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: str
    record_id: str


@dataclass
class ComparatorResult:
    """Aggregated results from all three providers for one comparison prompt."""

    prompt: str
    results: list[ProviderResult] = field(default_factory=list)


def build_comparator_chain(cfg: LCLGConfig) -> RunnableLambda[Any, ComparatorResult]:
    """Return a chain that takes {prompt} and returns a ComparatorResult.

    Always uses ChatAiGateway explicit mode for all three providers regardless of
    LCLG_MODE, because the Gemini connector requires an explicit action request.
    See docs/gateway-integration.md#gemini-in-proxy-mode for the rationale.
    """

    def make_provider_runner(provider: str, model: str) -> RunnableLambda[Any, ProviderResult]:
        """Build a single-provider runner that returns a ProviderResult with full metering."""
        labels: dict[str, str] = {"agent": "comparator", "provider": provider}
        if cfg.run_id:
            labels["run_id"] = cfg.run_id
        # Use the no-thinking subclass for Google/Gemini; standard class for all others.
        llm_cls = _ChatAiGatewayNoThinking if provider == "google" else ChatAiGateway
        llm = llm_cls(
            provider=provider,
            model=model,
            config=cfg.gateway,
            workload_id=WORKLOAD_COMPARATOR,
            labels=labels,
            max_tokens=1024,  # one provider response per call; sized for a full paragraph
        )

        def run(prompt: str) -> ProviderResult:
            # Retry up to 3 times for transient upstream errors (503, etc.).
            # The SDK returns empty content + zero tokens when the upstream
            # provider fails — until the SDK raises proper errors on non-2xx
            # upstream status, we detect failure by zero tokens_out.
            for attempt in range(3):
                if attempt > 0:
                    time.sleep(3 * attempt)  # 3s, 6s
                start = time.monotonic()
                # [AXEMERE] Use _generate() instead of invoke() for metering access
                # ChatAiGateway.invoke() returns an AIMessage; ChatAiGateway._generate() returns
                # the full LLMResult including generation_info, which carries the gateway
                # metering fields (tokens_in, tokens_out, cost_usd, record_id).
                # _generate() is a protected method on BaseChatModel — we call it here
                # deliberately to access per-generation metadata that invoke() discards.
                # Alternatives:
                #   A) Use invoke() and attach a _MeteringCallback — works but requires
                #      passing RunnableConfig and creates indirection between the call
                #      and the metering record.
                #   B) Post-call admin API lookup — covered in proxy_metering.py, but
                #      requires admin_token which isn't available in managed mode.
                # Docs: https://axemere.ai/docs/guides/developer-integration
                result = llm._generate([HumanMessage(content=prompt)])
                latency_ms = int((time.monotonic() - start) * 1000)

                gen = result.generations[0]
                info = gen.generation_info or {}
                metering = info.get("metering") or {}

                tokens_out = int(metering.get("tokens_out", 0))
                if tokens_out > 0 or attempt == 2:
                    break  # real response or exhausted retries

            return ProviderResult(
                provider=provider,
                model=model,
                response=str(gen.message.content),
                latency_ms=latency_ms,
                tokens_in=int(metering.get("tokens_in", 0)),
                tokens_out=tokens_out,
                cost_usd=str(metering.get("cost_usd", "0.00000")),
                record_id=str(info.get("record_id", "")),
            )

        return RunnableLambda(run)

    runners: dict[str, RunnableLambda[Any, ProviderResult]] = {
        p["key"]: make_provider_runner(p["provider"], p["model"]) for p in PROVIDERS
    }

    # [AXEMERE] RunnableParallel — concurrent multi-provider calls
    # All three provider calls start simultaneously. Total wall-clock time is
    # bounded by the slowest provider, not the sum. Each call gets its own
    # record_id in the gateway's execution log.
    # Docs: https://axemere.ai/docs/guides/developer-integration
    parallel: RunnableParallel[Any] = RunnableParallel(**runners)  # type: ignore[arg-type]

    def run_comparison(inp: dict[str, Any]) -> ComparatorResult:
        prompt = inp["prompt"]
        raw: dict[str, ProviderResult] = parallel.invoke(prompt)
        return ComparatorResult(
            prompt=prompt,
            results=[raw[p["key"]] for p in PROVIDERS],
        )

    return RunnableLambda(run_comparison)
