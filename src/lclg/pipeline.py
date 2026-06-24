"""Pipeline: orchestrate the five-agent research sequence."""

from __future__ import annotations

import contextlib
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.runnables import RunnableConfig

from lclg.agents import (
    build_analyst_chain,
    build_comparator_chain,
    build_planner_chain,
    build_reporter_chain,
    build_researcher_chain,
)
from lclg.agents.comparator import ComparatorResult
from lclg.agents.researcher import ResearchResult
from lclg.config import (
    WORKLOAD_ANALYST,
    WORKLOAD_COMPARATOR,
    WORKLOAD_PLANNER,
    WORKLOAD_REPORTER,
    WORKLOAD_RESEARCHER,
    LCLGConfig,
)
from lclg.proxy_metering import (
    extract_native_metering,
    fetch_record_metering,
    pop_record_id,
)


@dataclass
class AgentCall:
    """Record of a single gateway call, used to build the Attribution Breakdown.

    Fields come from three sources depending on mode:
    - ``record_id``: always captured via httpx event hook (proxy modes) or
      ``generation_info`` (explicit mode).
    - ``tokens_in``/``tokens_out``/``cost_usd``: from gateway metering in
      explicit mode, from admin API or native llm_output in proxy mode.
    - ``provider``/``model``: from gateway metadata or native llm_output.
    """

    agent: str
    provider: str
    model: str
    workload_id: str
    tokens_in: int
    tokens_out: int
    cost_usd: str
    record_id: str
    latency_ms: int


@dataclass
class PipelineResult:
    """Full output of a single pipeline run, used to render the HTML/MD report.

    Populated incrementally as each agent completes. ``calls`` is appended to by
    ``_MeteringCallback`` and, for the ComparatorAgent, directly by ``run_pipeline``.
    """

    run_id: str
    topic: str
    mode: str
    started_at: float
    finished_at: float

    sub_questions: list[str] = field(default_factory=list)
    research: list[ResearchResult] = field(default_factory=list)
    synthesis: str = ""
    comparison: ComparatorResult | None = None
    report: str = ""

    # Every gateway call, for the cost/attribution breakdown in the report.
    calls: list[AgentCall] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        """Sum of cost_usd across all agent calls; non-numeric values are skipped."""
        total = 0.0
        for call in self.calls:
            with contextlib.suppress(ValueError, TypeError):
                total += float(call.cost_usd)
        return total

    @property
    def total_latency_ms(self) -> int:
        """Wall-clock ms from pipeline start to ReportAgent completion."""
        return int((self.finished_at - self.started_at) * 1000)

    @property
    def topic_hash(self) -> str:
        """First 8 hex chars of SHA-256(topic); used as a stable short identifier."""
        return hashlib.sha256(self.topic.encode()).hexdigest()[:8]


class _MeteringCallback(BaseCallbackHandler):
    """Appends an AgentCall to result.calls when an LLM call completes.

    Works for both buffered (_generate) and streaming (_stream) — LangChain
    calls on_llm_end in both cases with the accumulated LLMResult.

    Metering data is sourced from three places in priority order:
    1. generation_info["metering"] — populated by ChatAiGateway (explicit mode).
    2. Admin API GET /v1/records/{id} — full gateway metering; requires
       MVGC_ADMIN_TOKEN; covers streaming calls where llm_output is None.
    3. response.llm_output — provider-native token counts from non-streaming
       invoke() calls (ChatOpenAI, ChatAnthropic). No cost data available.

    The gateway record ID (X-Mvgc-Record-Id) is captured from response headers
    via httpx event hooks injected by inject_*_hook() in the proxy mode builders.
    """

    def __init__(
        self,
        agent: str,
        workload_id: str,
        calls: list[AgentCall],
        t0: float,
        *,
        gateway_url: str = "",
        admin_token: str | None = None,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._workload_id = workload_id
        self._calls = calls
        self._t0 = t0
        self._gateway_url = gateway_url
        self._admin_token = admin_token

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        latency_ms = int((time.monotonic() - self._t0) * 1000)

        # Capture gateway record ID stored by the httpx event hook (proxy modes).
        # pop_record_id() reads thread-local storage, so parallel researcher calls
        # each get their own record ID without interference.
        captured_record_id = pop_record_id()

        # [AXEMERE] Proxy mode metering — native llm_output fallback
        # For invoke() calls, the provider SDK returns token counts in llm_output.
        # For streaming calls, llm_output is None; we fall back to the admin API.
        # ChatAiGateway explicit mode never reaches this path — it uses generation_info.
        native_tokens_in, native_tokens_out, native_model, native_provider = (
            extract_native_metering(response.llm_output)
        )

        for gen_list in response.generations:
            for gen in gen_list:
                info = getattr(gen, "generation_info", None) or {}
                metering = info.get("metering") or {}

                if metering:
                    # Path 1: ChatAiGateway explicit mode — full gateway metering in generation_info
                    tokens_in = int(metering.get("tokens_in", 0))
                    tokens_out = int(metering.get("tokens_out", 0))
                    cost_usd = str(metering.get("cost_usd", "0.00000"))
                    provider = info.get("provider", "")
                    model = info.get("model", "")
                    record_id = str(info.get("record_id") or captured_record_id)
                else:
                    record_id = captured_record_id

                    # [AXEMERE] Path 2: Admin API enrichment (self-hosted, streaming)
                    # When admin_token is set and we have a record_id (from the httpx
                    # hook), fetch full metering from the gateway. This is the only
                    # way to recover tokens and cost for streaming calls where the
                    # native providers return llm_output=None. The fetch is synchronous
                    # but local (localhost:7080), so latency overhead is < 50ms.
                    gateway_metering: dict[str, Any] = {}
                    if record_id and self._admin_token and not response.llm_output:
                        gateway_metering = fetch_record_metering(
                            self._gateway_url, record_id, self._admin_token
                        )

                    if gateway_metering:
                        tokens_in = gateway_metering["tokens_in"]
                        tokens_out = gateway_metering["tokens_out"]
                        cost_usd = gateway_metering["usd_charged"]
                        provider = gateway_metering.get("provider", "")
                        model = gateway_metering.get("model", native_model)
                    else:
                        # Path 3: Native llm_output (invoke mode, no admin token)
                        tokens_in = native_tokens_in
                        tokens_out = native_tokens_out
                        cost_usd = "0.00000"
                        provider = native_provider
                        model = native_model

                self._calls.append(
                    AgentCall(
                        agent=self._agent,
                        provider=provider,
                        model=model,
                        workload_id=self._workload_id,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        cost_usd=cost_usd,
                        record_id=record_id,
                        latency_ms=latency_ms,
                    )
                )


def run_pipeline(topic: str, cfg: LCLGConfig) -> PipelineResult:
    """Execute the full research pipeline for the given topic.

    Returns a PipelineResult with all intermediate outputs and gateway metering.
    """
    run_id = str(uuid.uuid4())[:8]
    cfg.run_id = run_id  # propagates to all gateway labels via _llm.py

    # Shared kwargs for every _MeteringCallback — enables admin API enrichment
    # for streaming agents in self-hosted mode (MVGC_ADMIN_TOKEN must be set).
    cb_kwargs: dict[str, Any] = {
        "gateway_url": cfg.gateway.gateway_url,
        "admin_token": cfg.admin_token,
    }

    result = PipelineResult(
        run_id=run_id,
        topic=topic,
        mode=cfg.mode,
        started_at=time.time(),
        finished_at=0.0,
    )

    # -----------------------------------------------------------------------
    # Step 1: Plan — decompose topic into sub-questions
    # -----------------------------------------------------------------------
    print(f"[planner] decomposing topic into {cfg.max_sub_questions} sub-questions...")
    planner = build_planner_chain(cfg)
    t0 = time.monotonic()
    sub_questions: list[str] = planner.invoke(
        {"topic": topic, "n": cfg.max_sub_questions},
        config=RunnableConfig(
            callbacks=[
                _MeteringCallback("planner", WORKLOAD_PLANNER, result.calls, t0, **cb_kwargs)
            ]
        ),
    )
    planner_ms = int((time.monotonic() - t0) * 1000)
    result.sub_questions = sub_questions[: cfg.max_sub_questions]
    print(f"[planner] {len(result.sub_questions)} sub-questions ({planner_ms}ms)")

    # -----------------------------------------------------------------------
    # Step 2: Research — gather facts for each sub-question in parallel
    # -----------------------------------------------------------------------
    print(f"[researcher] researching {len(result.sub_questions)} sub-questions in parallel...")
    researcher = build_researcher_chain(cfg)

    # [AXEMERE] Parallel research calls — one thread per sub-question
    # ThreadPoolExecutor runs N researcher.invoke() calls concurrently. Each call
    # gets its own _MeteringCallback instance so metering records don't interfere.
    # In proxy mode, pop_record_id() reads from thread-local storage, which is
    # safe because httpx fires event hooks on the thread that received the response
    # — the same thread that will call on_llm_end via the callback.
    # Alternatives:
    #   A) Sequential calls — simpler but N×slower; not viable for N≥3.
    #   B) LangChain RunnableParallel — same concurrency with a cleaner API,
    #      but requires all sub-questions upfront and loses per-call error isolation.
    # Docs: https://axemere.ai/docs/guides/developer-integration
    research_results: list[ResearchResult] = [None] * len(result.sub_questions)  # type: ignore
    with ThreadPoolExecutor(max_workers=len(result.sub_questions)) as pool:
        futures = {
            pool.submit(
                researcher.invoke,
                {"question": q},
                RunnableConfig(
                    callbacks=[
                        _MeteringCallback(
                            "researcher",
                            WORKLOAD_RESEARCHER,
                            result.calls,
                            time.monotonic(),
                            **cb_kwargs,
                        )
                    ]
                ),
            ): i
            for i, q in enumerate(result.sub_questions)
        }
        for future in as_completed(futures):
            idx = futures[future]
            research_results[idx] = future.result()

    result.research = [r for r in research_results if r is not None]
    sources = set(r.source for r in result.research)
    print(f"[researcher] complete — sources: {', '.join(sources)}")

    # -----------------------------------------------------------------------
    # Step 3: Analyse — synthesise findings
    # -----------------------------------------------------------------------
    print("[analyst] synthesising research findings...")
    analyst = build_analyst_chain(cfg)
    findings_text = "\n\n".join(f"Q: {r.question}\nA: {r.answer}" for r in result.research)
    t0 = time.monotonic()
    # [AXEMERE] Use streaming for the analyst to bypass ConnectorTimeout.
    # The analyst receives the full research findings text, which can be
    # thousands of tokens. On a self-hosted or Free Gateway with the default
    # 30s ConnectorTimeout, this frequently exceeds the limit. Streaming is
    # exempt from ConnectorTimeout — the same pattern used for the reporter.
    analyst_cb = _MeteringCallback("analyst", WORKLOAD_ANALYST, result.calls, t0, **cb_kwargs)
    analyst_chunks: list[str] = []
    for chunk in analyst.stream(
        {"topic": topic, "findings": findings_text},
        config=RunnableConfig(callbacks=[analyst_cb]),
    ):
        analyst_chunks.append(chunk)
    result.synthesis = "".join(analyst_chunks)
    analyst_ms = int((time.monotonic() - t0) * 1000)
    print(f"[analyst] synthesis complete ({analyst_ms}ms)")

    # -----------------------------------------------------------------------
    # Step 4: Compare — fan to three providers in parallel
    # -----------------------------------------------------------------------
    print("[comparator] fanning synthesis prompt to three providers...")
    comparator = build_comparator_chain(cfg)
    t0 = time.monotonic()
    result.comparison = comparator.invoke({"prompt": result.synthesis})
    comparator_ms = int((time.monotonic() - t0) * 1000)
    if result.comparison:
        providers_str = ", ".join(r.provider for r in result.comparison.results)
        print(f"[comparator] complete — {providers_str} ({comparator_ms}ms)")
        # Comparator reads metering directly from generation_info (not via callback)
        # because it uses ChatAiGateway._generate() directly for full response access.
        for pr in result.comparison.results:
            result.calls.append(
                AgentCall(
                    agent="comparator",
                    provider=pr.provider,
                    model=pr.model,
                    workload_id=WORKLOAD_COMPARATOR,
                    tokens_in=pr.tokens_in,
                    tokens_out=pr.tokens_out,
                    cost_usd=pr.cost_usd,
                    record_id=pr.record_id,
                    latency_ms=pr.latency_ms,
                )
            )

    # -----------------------------------------------------------------------
    # Step 5: Report — generate the final executive summary
    # -----------------------------------------------------------------------
    print("[reporter] generating final report...")
    reporter = build_reporter_chain(cfg)

    comparison_summary = ""
    if result.comparison:
        lines = []
        for pr in result.comparison.results:
            lines.append(
                f"**{pr.provider} ({pr.model})** — {pr.latency_ms}ms, "
                f"{pr.tokens_in}in/{pr.tokens_out}out, ${pr.cost_usd}\n"
                f"{pr.response[:500]}{'...' if len(pr.response) > 500 else ''}"
            )
        comparison_summary = "\n\n---\n\n".join(lines)

    # Truncate per-answer context: the synthesis already distils the full
    # content; the reporter only needs a brief excerpt per finding to cite sources.
    findings_summary = "\n\n".join(
        f"**{r.question}** [{r.source}]\n{r.answer[:1500]}{'...' if len(r.answer) > 1500 else ''}"
        for r in result.research
    )

    reporter_input = {
        "topic": topic,
        "findings_summary": findings_summary,
        "synthesis": result.synthesis,
        "comparison_summary": comparison_summary,
    }

    t0 = time.monotonic()
    # [AXEMERE] Use streaming for the reporter to bypass ConnectorTimeout.
    # The gateway's ConnectorTimeout only applies to buffered requests. The
    # reporter sends the largest prompt in the pipeline and can exceed that
    # limit when using claude-sonnet-4-6. Streaming (gateway >= v0.58.44)
    # forwards stream=true to Anthropic so tokens arrive immediately and the
    # connection is never cancelled. The _MeteringCallback captures the
    # gateway_metering SSE event injected before message_stop.
    reporter_cb = _MeteringCallback("reporter", WORKLOAD_REPORTER, result.calls, t0, **cb_kwargs)
    chunks: list[str] = []
    for chunk in reporter.stream(reporter_input, config=RunnableConfig(callbacks=[reporter_cb])):
        chunks.append(chunk)
    result.report = "".join(chunks)
    reporter_ms = int((time.monotonic() - t0) * 1000)
    print(f"[reporter] report complete ({reporter_ms}ms)")

    result.finished_at = time.time()
    print(f"\nPipeline complete — run_id={run_id}, total cost=${result.total_cost_usd:.5f}")
    return result
