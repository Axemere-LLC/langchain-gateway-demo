"""Tests for the report builder."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from lclg.agents.comparator import ComparatorResult, ProviderResult
from lclg.agents.researcher import ResearchResult
from lclg.pipeline import AgentCall, PipelineResult
from lclg.report.builder import _from_json, _to_json, build_report
from lclg.report.markdown import render_markdown


def _make_result() -> PipelineResult:
    now = time.time()
    return PipelineResult(
        run_id="abc12345",
        topic="solid state batteries",
        mode="explicit-selfhosted",
        started_at=now,
        finished_at=now + 10.5,
        sub_questions=["What is X?", "How does Y work?"],
        research=[
            ResearchResult(
                question="What is X?",
                answer="X is a thing.",
                source="model_knowledge",
            ),
            ResearchResult(
                question="How does Y work?",
                answer="Y works like this.",
                source="web_search",
                urls=["https://example.com"],
            ),
        ],
        synthesis="Key findings synthesis.",
        comparison=ComparatorResult(
            prompt="Summarise this.",
            results=[
                ProviderResult(
                    provider="openai",
                    model="gpt-4o",
                    response="OpenAI response.",
                    latency_ms=800,
                    tokens_in=100,
                    tokens_out=200,
                    cost_usd="0.00300",
                    record_id="rec-oai-001",
                ),
                ProviderResult(
                    provider="anthropic",
                    model="claude-sonnet-4-6",
                    response="Anthropic response.",
                    latency_ms=950,
                    tokens_in=110,
                    tokens_out=190,
                    cost_usd="0.00350",
                    record_id="rec-ant-001",
                ),
                ProviderResult(
                    provider="google",
                    model="gemini-1.5-pro",
                    response="Google response.",
                    latency_ms=700,
                    tokens_in=95,
                    tokens_out=210,
                    cost_usd="0.00200",
                    record_id="rec-gem-001",
                ),
            ],
        ),
        report="# Report\n\nExecutive summary here.\n\n## Recommendations\n\n1. Do X.",
        calls=[
            AgentCall(
                agent="planner",
                provider="openai",
                model="gpt-4o-mini",
                workload_id="wl_lclg_planner",
                tokens_in=50,
                tokens_out=80,
                cost_usd="0.00010",
                record_id="rec-plan-001",
                latency_ms=300,
            ),
        ],
    )


class TestBuildReport:
    def test_writes_three_files(self, tmp_path: Path) -> None:
        result = _make_result()
        paths = build_report(result, str(tmp_path))

        assert "html" in paths
        assert "markdown" in paths
        assert "json" in paths
        assert paths["html"].exists()
        assert paths["markdown"].exists()
        assert paths["json"].exists()

    def test_files_are_in_run_subdirectory(self, tmp_path: Path) -> None:
        result = _make_result()
        paths = build_report(result, str(tmp_path))

        for path in paths.values():
            assert path.parent.name == result.run_id

    def test_html_contains_topic(self, tmp_path: Path) -> None:
        result = _make_result()
        paths = build_report(result, str(tmp_path))
        html = paths["html"].read_text()
        assert "solid state batteries" in html

    def test_html_is_self_contained(self, tmp_path: Path) -> None:
        result = _make_result()
        paths = build_report(result, str(tmp_path))
        html = paths["html"].read_text()
        assert "<style>" in html
        assert "mermaid" in html

    def test_markdown_contains_cost(self, tmp_path: Path) -> None:
        result = _make_result()
        paths = build_report(result, str(tmp_path))
        md = paths["markdown"].read_text()
        assert "$" in md
        assert result.run_id in md


class TestJsonRoundtrip:
    def test_serialise_deserialise(self) -> None:
        original = _make_result()
        json_str = _to_json(original)
        restored = _from_json(json_str)

        assert restored.run_id == original.run_id
        assert restored.topic == original.topic
        assert len(restored.research) == len(original.research)
        assert restored.research[0].source == "model_knowledge"
        assert restored.research[1].source == "web_search"
        assert restored.comparison is not None
        assert len(restored.comparison.results) == 3
        assert restored.total_cost_usd == pytest.approx(original.total_cost_usd)


class TestRenderMarkdown:
    def test_contains_all_sections(self) -> None:
        result = _make_result()
        md = render_markdown(result)

        assert "## Research Findings" in md
        assert "## Analysis Synthesis" in md
        assert "## Provider Comparison" in md
        assert "## Executive Report" in md
        assert "## Cost Summary" in md
        assert "## Attribution Breakdown" in md

    def test_source_badges_present(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        assert "[Model Knowledge]" in md
        assert "[Web Search]" in md

    def test_total_cost_consistent(self) -> None:
        result = _make_result()
        md = render_markdown(result)
        # The grand total from calls (one call at $0.00010)
        assert "0.00010" in md
