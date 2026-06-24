"""PlannerAgent: decompose a research topic into focused sub-questions."""

from __future__ import annotations

import json

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

from lclg.agents._llm import build_llm
from lclg.config import WORKLOAD_PLANNER, LCLGConfig

# [AXEMERE] model-tier routing — fast/cheap for decomposition
# The PlannerAgent uses gpt-4o-mini because topic decomposition is a simple
# structured task: it does not require frontier reasoning, just reliable JSON
# output. Using a cheaper model here saves cost across every pipeline run since
# the planner runs once before the parallel research phase.
# Alternatives:
#   A) Use claude-haiku-4-5 — equally cheap, Anthropic provider for diversity.
#   B) Use gpt-4o — more reliable JSON but 10x the cost for negligible gain here.
# Docs: https://axemere.ai/docs/guides/configuration/workloads
PROVIDER = "openai"
MODEL = "gpt-4o-mini"

_SYSTEM = """\
You are a research planner. Given a topic, produce a JSON array of focused sub-questions
that together cover the topic thoroughly. Each sub-question should be specific and answerable
in a short paragraph.

Respond ONLY with a valid JSON array of strings. No explanation, no markdown fences.
Example: ["What is X?", "How does Y work?", "What are the limitations of Z?"]
"""

_HUMAN = "Topic: {topic}\n\nProduce exactly {n} sub-questions."


def build_planner_chain(cfg: LCLGConfig) -> Runnable:
    """Return a chain that takes {topic, n} and returns a list[str] of sub-questions."""
    llm = build_llm(
        cfg,
        provider=PROVIDER,
        model=MODEL,
        workload_id=WORKLOAD_PLANNER,
        labels={"agent": "planner"},
        max_tokens=512,
    )

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

    def parse_sub_questions(text: str) -> list[str]:
        text = text.strip()
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return [str(q) for q in result]
        except json.JSONDecodeError:
            pass
        # Fallback: strip leading list markers (digits, dots, dashes, parens, spaces)
        # to handle numbered lists like "1. Question?" or "1) Question?".
        lines = [ln.lstrip("0123456789.-) ").strip() for ln in text.splitlines()]
        return [ln for ln in lines if ln]

    return prompt | llm | StrOutputParser() | RunnableLambda(parse_sub_questions)
