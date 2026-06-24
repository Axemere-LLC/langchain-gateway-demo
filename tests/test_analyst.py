"""Tests for AnalysisAgent."""

from __future__ import annotations

from unittest.mock import patch

from conftest import make_runnable_llm

from lclg.agents.analyst import build_analyst_chain
from lclg.config import LCLGConfig


class TestAnalystChain:
    def test_returns_string(self, cfg: LCLGConfig) -> None:
        mock_llm = make_runnable_llm("Synthesis of findings.")

        with patch("lclg.agents.analyst.build_llm", return_value=mock_llm):
            chain = build_analyst_chain(cfg)
            result = chain.invoke({"topic": "batteries", "findings": "Finding 1\nFinding 2"})

        assert isinstance(result, str)
        assert "Synthesis" in result

    def test_uses_mistral_provider(self, cfg: LCLGConfig) -> None:
        from lclg.agents.analyst import PROVIDER

        assert PROVIDER == "mistral"

    def test_uses_correct_workload(self, cfg: LCLGConfig) -> None:
        from lclg.config import WORKLOAD_ANALYST

        captured: list[str] = []

        def fake_build(cfg, *, workload_id, **kw):
            captured.append(workload_id)
            return make_runnable_llm("synthesis")

        with patch("lclg.agents.analyst.build_llm", side_effect=fake_build):
            chain = build_analyst_chain(cfg)
            chain.invoke({"topic": "t", "findings": "f"})

        assert captured[0] == WORKLOAD_ANALYST
