"""ReportAgent: generate the final executive summary from all pipeline outputs."""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from lclg.agents._llm import build_llm
from lclg.config import WORKLOAD_REPORTER, LCLGConfig

# [AXEMERE] high-capability model for the final artifact
# The ReportAgent uses claude-sonnet-4-6 because the final report is the
# primary deliverable — quality matters more than cost here. This is the only
# agent run after the ComparatorAgent, so it runs once per pipeline execution.
# Streaming is used (see pipeline.py) to bypass the gateway's ConnectorTimeout
# on large prompts — requires gateway >= v0.58.44 (Stream field added to
# anthropicRequest in connectors/anthropic/connector.go).
# Alternatives:
#   A) gpt-4o — equivalent quality, faster; use if Anthropic access is unavailable.
#   B) claude-haiku-4-5 — much cheaper; acceptable for internal use.
# Docs: https://axemere.ai/docs/guides/configuration/workloads
PROVIDER = "anthropic"
MODEL = "claude-sonnet-4-6"

_SYSTEM = """\
You are an expert analyst and writer producing an executive research report.
You have access to: research findings, an analytical synthesis, and a side-by-side
comparison of responses from three leading AI providers on the same question.

Your report should:
1. Open with a 2-3 sentence executive summary
2. Present key findings in clear, numbered sections
3. Note where the three AI providers agreed and diverged
4. Close with 3-5 actionable recommendations
5. Use professional, accessible language — no jargon without explanation

Format your response in clean Markdown with ## headings for each section.
"""

_HUMAN = """\
Topic: {topic}

## Research Findings
{findings_summary}

## Analytical Synthesis
{synthesis}

## Provider Comparison Summary
{comparison_summary}

Write the executive research report."""


def build_reporter_chain(cfg: LCLGConfig) -> Runnable:
    """Return a chain that takes {topic, findings_summary, synthesis, comparison_summary}
    and returns the final report as a Markdown string."""
    llm = build_llm(
        cfg,
        provider=PROVIDER,
        model=MODEL,
        workload_id=WORKLOAD_REPORTER,
        labels={"agent": "reporter"},
        max_tokens=2048,
    )

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

    return prompt | llm | StrOutputParser()
