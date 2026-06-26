"""ResearchAgent: gather facts for a sub-question via web search or model knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda

from lclg.agents._llm import build_llm
from lclg.config import WORKLOAD_RESEARCHER, LCLGConfig

# [AXEMERE] model-tier routing — fast/cheap for high-volume research calls
# The ResearchAgent calls N times in parallel (once per sub-question). Using
# claude-haiku-4-5 keeps per-call cost low while maintaining quality for
# fact-retrieval tasks. The gateway manages the Anthropic credential; no
# ANTHROPIC_API_KEY is needed locally.
# Alternatives:
#   A) claude-sonnet-4-6 — higher quality but 10x cost; reasonable for N≤2.
#   B) gpt-4o-mini — OpenAI equivalent; demonstrates provider diversity.
# Docs: https://axemere.ai/docs/guides/configuration/workloads
PROVIDER = "anthropic"
MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_WEB = """\
You are a research assistant with access to a web search tool. Use it to find
current, factual information to answer the question. Cite your sources when possible.
Keep your answer focused and under 300 words.
"""

_SYSTEM_MODEL = """\
You are a knowledgeable research assistant. Answer the following question using
your training knowledge. Be factual, concise, and note any uncertainty.
Keep your answer under 300 words.
"""

_HUMAN = "Question: {question}"


@dataclass
class ResearchResult:
    """Single research finding for one sub-question.

    ``source`` is one of:
    - ``"web_search"`` — answer was grounded by live Tavily search results
    - ``"model_knowledge"`` — answer came from the model's training data only
    """

    question: str
    answer: str
    source: str
    urls: list[str] = field(default_factory=list)


def build_researcher_chain(cfg: LCLGConfig) -> Runnable:
    """Return a chain that takes {question} and returns a ResearchResult.

    Uses Tavily web search when TAVILY_API_KEY is set; falls back to model
    knowledge otherwise. The source field in the result records which path ran.
    """
    # [AXEMERE] LangChain tool use through the gateway
    # When tool calling is active, the gateway still governs the LLM invocation
    # that decides which tools to call and synthesises the results. The tool
    # execution itself (the Tavily HTTP request) happens outside the gateway —
    # only LLM calls are governed.
    # Docs: https://axemere.ai/docs/guides/developer-integration
    tavily_key = cfg.tavily_api_key

    llm = build_llm(
        cfg,
        provider=PROVIDER,
        model=MODEL,
        workload_id=WORKLOAD_RESEARCHER,
        labels={"agent": "researcher"},
        max_tokens=768,  # one focused answer ~300 words; 256 default would truncate
    )

    if tavily_key:
        return _build_web_chain(llm, tavily_key)
    return _build_model_chain(llm)


def _build_web_chain(llm: Any, tavily_key: str) -> Runnable:
    """Research chain that uses Tavily web search."""
    from langchain_tavily import TavilySearch

    search_tool = TavilySearch(
        api_key=tavily_key,
        max_results=3,
    )
    llm_with_tools = llm.bind_tools([search_tool])

    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM_WEB), ("human", _HUMAN)])

    def run_with_tools(question: str) -> ResearchResult:
        messages = prompt.format_messages(question=question)
        response: AIMessage = llm_with_tools.invoke(messages)

        urls: list[str] = []
        answer = str(response.content) if response.content else ""

        # If the model called the search tool, execute it and get a final answer
        if response.tool_calls:
            from langchain_core.messages import ToolMessage

            tool_messages = []
            for tc in response.tool_calls:
                result = search_tool.invoke(tc["args"])
                # Collect source URLs from tool output
                if isinstance(result, list):
                    for r in result:
                        if isinstance(r, dict) and r.get("url"):
                            urls.append(r["url"])
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                    )
                )
            # Second LLM call to synthesise the search results
            final = llm_with_tools.invoke(messages + [response] + tool_messages)
            answer = str(final.content) if final.content else ""

        return ResearchResult(
            question=question,
            answer=answer,
            source="web_search",
            urls=urls,
        )

    return RunnableLambda(lambda inp: run_with_tools(inp["question"]))


def _build_model_chain(llm: Any) -> Runnable:
    """Research chain that uses model training knowledge only."""
    prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM_MODEL), ("human", _HUMAN)])

    def run_model(question: str) -> ResearchResult:
        messages = prompt.format_messages(question=question)
        response: AIMessage = llm.invoke(messages)
        return ResearchResult(
            question=question,
            answer=str(response.content),
            source="model_knowledge",
        )

    return RunnableLambda(lambda inp: run_model(inp["question"]))
