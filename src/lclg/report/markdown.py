"""Render a PipelineResult as a Markdown report."""

from __future__ import annotations

from datetime import UTC, datetime

from lclg.pipeline import PipelineResult


def render_markdown(result: PipelineResult) -> str:
    """Render ``result`` as a Markdown string.

    The output uses GitHub-flavored Markdown: ATX headings, fenced Mermaid
    code blocks for the pipeline diagram, and standard pipe tables for the
    cost and attribution breakdowns.
    """
    ts = datetime.fromtimestamp(result.started_at, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    # --- Header ---
    lines += [
        f"# Research Report: {result.topic}",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Run ID | `{result.run_id}` |",
        f"| Timestamp | {ts} |",
        f"| Mode | `{result.mode}` |",
        f"| Total cost | ${result.total_cost_usd:.5f} |",
        f"| Total latency | {result.total_latency_ms:,}ms |",
        "",
    ]

    # --- Pipeline diagram ---
    lines += [
        "## Pipeline",
        "",
        "```mermaid",
        "flowchart LR",
        '  Planner["PlannerAgent"] --> Research',
        f'  subgraph Research["Research × {len(result.sub_questions)}"]',
    ]
    for i, q in enumerate(result.sub_questions):
        short = q[:40] + "..." if len(q) > 40 else q
        lines.append(f'    R{i}["{short}"]')
    lines += [
        "  end",
        "  Research --> Analyst",
        '  Analyst["AnalysisAgent"] --> Comparator',
        '  subgraph Compare["Comparator (parallel)"]',
        '    OAI["OpenAI gpt-4o"]',
        '    ANT["Anthropic claude-sonnet-4-6"]',
        '    GEM["Gemini gemini-2.5-flash"]',
        "  end",
        "  Comparator --> Reporter",
        '  Reporter["ReportAgent"] --> Output[("Report")]',
        "```",
        "",
    ]

    # --- Research findings ---
    lines += ["## Research Findings", ""]
    for r in result.research:
        source_badge = f"[{r.source.replace('_', ' ').title()}]"
        lines += [
            f"### {r.question} {source_badge}",
            "",
            r.answer,
            "",
        ]
        if r.urls:
            lines += ["**Sources:**"] + [f"- {u}" for u in r.urls] + [""]

    # --- Synthesis ---
    lines += ["## Analysis Synthesis", "", result.synthesis, ""]

    # --- Provider comparison ---
    if result.comparison and result.comparison.results:
        lines += ["## Provider Comparison", ""]
        headers = ["Provider", "Model", "Latency (ms)", "Tokens In", "Tokens Out", "Cost (USD)"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for pr in result.comparison.results:
            lines.append(
                f"| {pr.provider} | {pr.model} | {pr.latency_ms:,} | "
                f"{pr.tokens_in:,} | {pr.tokens_out:,} | ${pr.cost_usd} |"
            )
        lines += [""]

        for pr in result.comparison.results:
            lines += [f"### {pr.provider} ({pr.model})", "", pr.response, ""]

    # --- Final report ---
    lines += ["## Executive Report", "", result.report, ""]

    # --- Cost summary ---
    lines += [
        "## Cost Summary",
        "",
        "### By Agent",
        "",
        "| Agent | Model | Provider | Workload | Tokens In | Tokens Out | Cost (USD) |",
        "|-------|-------|----------|----------|-----------|------------|------------|",
    ]
    for call in result.calls:
        lines.append(
            f"| {call.agent} | {call.model} | {call.provider} | "
            f"`{call.workload_id}` | {call.tokens_in:,} | {call.tokens_out:,} | "
            f"${call.cost_usd} |"
        )
    lines += [
        f"| **Total** | | | | | | **${result.total_cost_usd:.5f}** |",
        "",
    ]

    # --- Attribution breakdown ---
    lines += [
        "## Attribution Breakdown",
        "",
        "| Agent | Model | Provider | Workload | Record ID | Tokens In | Tokens Out | Cost (USD) | Decision |",
        "|-------|-------|----------|----------|-----------|-----------|------------|------------|----------|",
    ]
    for call in result.calls:
        lines.append(
            f"| {call.agent} | {call.model} | {call.provider} | "
            f"`{call.workload_id}` | `{call.record_id[:8]}...` | "
            f"{call.tokens_in:,} | {call.tokens_out:,} | ${call.cost_usd} | allow |"
        )
    lines += [
        f"| **Total** | | | | | | | **${result.total_cost_usd:.5f}** | |",
        "",
    ]

    return "\n".join(lines)
