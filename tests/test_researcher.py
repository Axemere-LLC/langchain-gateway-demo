"""Tests for ResearchAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from lclg.agents.researcher import ResearchResult, build_researcher_chain
from lclg.config import LCLGConfig


def _make_mock_llm(content: str = "test answer") -> MagicMock:
    """Make a mock LLM whose invoke() returns an AIMessage."""
    mock = MagicMock()
    mock.invoke.return_value = AIMessage(content=content)
    mock.bind_tools.return_value = mock
    return mock


class TestResearcherChain:
    def test_returns_research_result(self, cfg: LCLGConfig) -> None:
        mock_llm = _make_mock_llm("Here are the facts.")

        with patch("lclg.agents.researcher.build_llm", return_value=mock_llm):
            chain = build_researcher_chain(cfg)
            result = chain.invoke({"question": "What is X?"})

        assert isinstance(result, ResearchResult)
        assert result.question == "What is X?"
        assert result.answer == "Here are the facts."

    def test_source_is_model_knowledge_without_tavily(self, cfg: LCLGConfig) -> None:
        assert cfg.tavily_api_key is None
        mock_llm = _make_mock_llm("Model answer.")

        with patch("lclg.agents.researcher.build_llm", return_value=mock_llm):
            chain = build_researcher_chain(cfg)
            result = chain.invoke({"question": "Q?"})

        assert result.source == "model_knowledge"
        assert result.urls == []

    def test_source_is_web_search_with_tavily(self, cfg_with_tavily: LCLGConfig) -> None:
        assert cfg_with_tavily.tavily_api_key is not None
        mock_llm = _make_mock_llm("Web answer.")

        with (
            patch("lclg.agents.researcher.build_llm", return_value=mock_llm),
            patch("langchain_tavily.TavilySearch") as mock_tavily_cls,
        ):
            mock_tavily = MagicMock()
            mock_tavily_cls.return_value = mock_tavily

            chain = build_researcher_chain(cfg_with_tavily)
            result = chain.invoke({"question": "Q?"})

        assert result.source == "web_search"

    def test_uses_correct_workload(self, cfg: LCLGConfig) -> None:
        from lclg.config import WORKLOAD_RESEARCHER

        captured: list[str] = []

        def fake_build(cfg, *, workload_id, **kw):
            captured.append(workload_id)
            return _make_mock_llm("ans")

        with patch("lclg.agents.researcher.build_llm", side_effect=fake_build):
            chain = build_researcher_chain(cfg)
            chain.invoke({"question": "Q?"})

        assert captured[0] == WORKLOAD_RESEARCHER
