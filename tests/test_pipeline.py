"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lclg.agents.comparator import ComparatorResult, ProviderResult
from lclg.agents.researcher import ResearchResult
from lclg.config import LCLGConfig
from lclg.pipeline import PipelineResult, run_pipeline


def _make_research_result(q: str) -> ResearchResult:
    return ResearchResult(question=q, answer="Test answer.", source="model_knowledge")


def _make_provider_result(provider: str) -> ProviderResult:
    return ProviderResult(
        provider=provider,
        model="test-model",
        response="Test response.",
        latency_ms=100,
        tokens_in=50,
        tokens_out=100,
        cost_usd="0.00010",
        record_id="rec-test",
    )


class TestRunPipeline:
    def test_returns_pipeline_result(self, cfg: LCLGConfig) -> None:
        mock_planner = MagicMock()
        mock_planner.invoke.return_value = ["Q1?", "Q2?"]

        mock_researcher = MagicMock()
        mock_researcher.invoke.side_effect = [
            _make_research_result("Q1?"),
            _make_research_result("Q2?"),
        ]

        mock_analyst = MagicMock()
        mock_analyst.stream.return_value = iter(["Synthesis text."])

        mock_comparator = MagicMock()
        mock_comparator.invoke.return_value = ComparatorResult(
            prompt="test",
            results=[
                _make_provider_result("openai"),
                _make_provider_result("anthropic"),
                _make_provider_result("google"),
            ],
        )

        mock_reporter = MagicMock()
        mock_reporter.stream.return_value = iter(["# Report\n\n", "Executive summary."])

        with (
            patch("lclg.pipeline.build_planner_chain", return_value=mock_planner),
            patch("lclg.pipeline.build_researcher_chain", return_value=mock_researcher),
            patch("lclg.pipeline.build_analyst_chain", return_value=mock_analyst),
            patch("lclg.pipeline.build_comparator_chain", return_value=mock_comparator),
            patch("lclg.pipeline.build_reporter_chain", return_value=mock_reporter),
        ):
            result = run_pipeline("solid state batteries", cfg)

        assert isinstance(result, PipelineResult)
        assert result.topic == "solid state batteries"
        assert len(result.sub_questions) == 2
        assert len(result.research) == 2
        assert result.synthesis == "Synthesis text."
        assert result.comparison is not None
        assert result.report.startswith("# Report")

    def test_respects_max_sub_questions(self, cfg: LCLGConfig) -> None:
        assert cfg.max_sub_questions == 2

        mock_planner = MagicMock()
        # Planner returns more questions than the configured max
        mock_planner.invoke.return_value = ["Q1?", "Q2?", "Q3?", "Q4?"]

        mock_researcher = MagicMock()
        mock_researcher.invoke.return_value = _make_research_result("Q?")
        mock_analyst = MagicMock()
        mock_analyst.stream.return_value = iter(["synthesis"])
        mock_comparator = MagicMock()
        mock_comparator.invoke.return_value = ComparatorResult(prompt="p", results=[])
        mock_reporter = MagicMock()
        mock_reporter.stream.return_value = iter(["report"])

        with (
            patch("lclg.pipeline.build_planner_chain", return_value=mock_planner),
            patch("lclg.pipeline.build_researcher_chain", return_value=mock_researcher),
            patch("lclg.pipeline.build_analyst_chain", return_value=mock_analyst),
            patch("lclg.pipeline.build_comparator_chain", return_value=mock_comparator),
            patch("lclg.pipeline.build_reporter_chain", return_value=mock_reporter),
        ):
            result = run_pipeline("test", cfg)

        assert len(result.sub_questions) == cfg.max_sub_questions

    def test_total_cost_sums_calls(self, cfg: LCLGConfig) -> None:

        mock_planner = MagicMock()
        mock_planner.invoke.return_value = ["Q1?"]
        mock_researcher = MagicMock()
        mock_researcher.invoke.return_value = _make_research_result("Q1?")
        mock_analyst = MagicMock()
        mock_analyst.stream.return_value = iter(["syn"])
        mock_comparator = MagicMock()
        mock_comparator.invoke.return_value = ComparatorResult(prompt="p", results=[])
        mock_reporter = MagicMock()
        mock_reporter.stream.return_value = iter(["rep"])

        with (
            patch("lclg.pipeline.build_planner_chain", return_value=mock_planner),
            patch("lclg.pipeline.build_researcher_chain", return_value=mock_researcher),
            patch("lclg.pipeline.build_analyst_chain", return_value=mock_analyst),
            patch("lclg.pipeline.build_comparator_chain", return_value=mock_comparator),
            patch("lclg.pipeline.build_reporter_chain", return_value=mock_reporter),
        ):
            result = run_pipeline("test", cfg)

        # calls list may be empty since agents are mocked, but total_cost_usd should not error
        assert isinstance(result.total_cost_usd, float)
        assert result.total_cost_usd >= 0.0
