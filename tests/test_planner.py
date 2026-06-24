"""Tests for PlannerAgent."""

from __future__ import annotations

import json
from unittest.mock import patch

from conftest import make_runnable_llm

from lclg.agents.planner import build_planner_chain
from lclg.config import LCLGConfig


class TestPlannerChain:
    def test_returns_list_of_strings(self, cfg: LCLGConfig) -> None:
        sub_questions = ["What is X?", "How does Y work?"]
        with patch(
            "lclg.agents.planner.build_llm",
            return_value=make_runnable_llm(json.dumps(sub_questions)),
        ):
            result = build_planner_chain(cfg).invoke({"topic": "test topic", "n": 2})

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(q, str) for q in result)

    def test_parses_json_array(self, cfg: LCLGConfig) -> None:
        payload = '["Question one?", "Question two?", "Question three?"]'
        with patch("lclg.agents.planner.build_llm", return_value=make_runnable_llm(payload)):
            result = build_planner_chain(cfg).invoke({"topic": "batteries", "n": 3})

        assert result == ["Question one?", "Question two?", "Question three?"]

    def test_fallback_parses_numbered_list(self, cfg: LCLGConfig) -> None:
        with patch(
            "lclg.agents.planner.build_llm",
            return_value=make_runnable_llm("1. What is X?\n2. How does Y work?"),
        ):
            result = build_planner_chain(cfg).invoke({"topic": "test", "n": 2})

        assert len(result) == 2
        assert result[0] == "What is X?"

    def test_uses_correct_workload(self, cfg: LCLGConfig) -> None:
        from lclg.config import WORKLOAD_PLANNER

        captured_workload: list[str] = []

        def fake_build_llm(cfg, *, provider, model, workload_id, **kw):
            captured_workload.append(workload_id)
            return make_runnable_llm('["Q1?"]')

        with patch("lclg.agents.planner.build_llm", side_effect=fake_build_llm):
            build_planner_chain(cfg).invoke({"topic": "t", "n": 1})

        assert captured_workload[0] == WORKLOAD_PLANNER
