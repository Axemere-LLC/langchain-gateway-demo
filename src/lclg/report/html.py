"""Render a PipelineResult as a self-contained HTML report via Jinja2."""

from __future__ import annotations

import contextlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from lclg.pipeline import AgentCall, PipelineResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(ms: int) -> str:
    total_s = int(ms) // 1000
    minutes = total_s // 60
    seconds = total_s % 60
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


_AGENT_ORDER = ["planner", "researcher", "analyst", "comparator", "reporter"]


def _agent_summary(calls: list[AgentCall]) -> list[dict[str, Any]]:
    """Aggregate calls by agent — returns rows in pipeline order."""
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "providers": set()}
    )
    for call in calls:
        g = groups[call.agent]
        g["calls"] += 1
        g["tokens_in"] += call.tokens_in
        g["tokens_out"] += call.tokens_out
        with contextlib.suppress(ValueError, TypeError):
            g["cost_usd"] += float(call.cost_usd)
        if call.provider:
            g["providers"].add(call.provider)

    rows = []
    for name in _AGENT_ORDER:
        if name in groups:
            g = groups[name]
            rows.append(
                {
                    "agent": name,
                    "calls": g["calls"],
                    "tokens_in": g["tokens_in"],
                    "tokens_out": g["tokens_out"],
                    "cost_usd": g["cost_usd"],
                    "providers": ", ".join(sorted(g["providers"])),
                }
            )
    return rows


def render_html(result: PipelineResult) -> str:
    """Render ``result`` as a self-contained HTML string via Jinja2.

    The returned string embeds all CSS inline and includes a Mermaid CDN
    script tag for pipeline diagram rendering. No external assets are needed
    at render time — only when the HTML is opened in a browser.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["format_timestamp"] = _format_timestamp
    env.filters["format_duration"] = _format_duration
    template = env.get_template("report.html.jinja2")
    return template.render(result=result, agent_summary=_agent_summary(result.calls))
