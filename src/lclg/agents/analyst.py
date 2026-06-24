"""AnalysisAgent: synthesise research findings into a coherent narrative."""

from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from lclg.agents._llm import build_llm
from lclg.config import WORKLOAD_ANALYST, LCLGConfig

# [AXEMERE] provider diversity — Mistral for synthesis
# The AnalysisAgent uses mistral-large-latest to demonstrate that the gateway
# manages credentials for providers beyond OpenAI and Anthropic. Synthesis
# requires reasoning across multiple sources, making it a good fit for a
# mid-tier model with strong instruction following.
# The gateway's openai_compat connector handles Mistral's API transparently —
# the client code is identical to an OpenAI call.
# Alternatives:
#   A) claude-sonnet-4-6 — high capability; use if Mistral access is unavailable.
#   B) gpt-4o — equivalent quality; use to keep everything on one provider.
# Docs: https://axemere.ai/docs/guides/configuration/providers
PROVIDER = "mistral"
MODEL = "mistral-large-latest"

_SYSTEM = """\
You are an expert analyst. You will receive a set of research findings on a topic.
Synthesise them into a coherent, well-structured narrative that:
- Identifies the key themes and patterns across findings
- Notes areas of agreement and disagreement between sources
- Highlights the most important and actionable insights
- Flags any gaps or uncertainties in the research

Write in clear, professional prose. Aim for 400-600 words.
"""

_HUMAN = """\
Topic: {topic}

Research Findings:
{findings}

Provide your synthesis."""


def build_analyst_chain(cfg: LCLGConfig) -> Runnable:
    """Return a chain that takes {topic, findings} and returns a synthesis string."""
    llm = build_llm(
        cfg,
        provider=PROVIDER,
        model=MODEL,
        workload_id=WORKLOAD_ANALYST,
        labels={"agent": "analyst"},
        max_tokens=1024,
    )

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

    return prompt | llm | StrOutputParser()
