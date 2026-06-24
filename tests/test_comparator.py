"""Tests for ComparatorAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from lclg.agents.comparator import PROVIDERS, ComparatorResult, build_comparator_chain
from lclg.config import LCLGConfig


def _mock_chat_ai_gateway(provider: str, model: str, **kw) -> MagicMock:
    mock = MagicMock()
    mock._generate.return_value = ChatResult(
        generations=[
            ChatGeneration(
                message=AIMessage(content=f"Response from {provider}"),
                generation_info={
                    "record_id": f"rec-{provider}-001",
                    "metering": {
                        "cost_usd": "0.00050",
                        "tokens_in": 100,
                        "tokens_out": 200,
                    },
                    "provider": provider,
                    "model": model,
                },
            )
        ]
    )
    return mock


class TestComparatorChain:
    def test_returns_comparator_result(self, cfg: LCLGConfig) -> None:
        with patch("lclg.agents.comparator.ChatAiGateway", side_effect=_mock_chat_ai_gateway):
            chain = build_comparator_chain(cfg)
            result = chain.invoke({"prompt": "Summarise this."})

        assert isinstance(result, ComparatorResult)
        assert len(result.results) == len(PROVIDERS)

    def test_all_three_providers_present(self, cfg: LCLGConfig) -> None:
        with patch("lclg.agents.comparator.ChatAiGateway", side_effect=_mock_chat_ai_gateway):
            chain = build_comparator_chain(cfg)
            result = chain.invoke({"prompt": "test"})

        provider_names = {r.provider for r in result.results}
        assert "openai" in provider_names
        assert "anthropic" in provider_names
        assert "google" in provider_names

    def test_captures_latency(self, cfg: LCLGConfig) -> None:
        with patch("lclg.agents.comparator.ChatAiGateway", side_effect=_mock_chat_ai_gateway):
            chain = build_comparator_chain(cfg)
            result = chain.invoke({"prompt": "test"})

        for pr in result.results:
            assert pr.latency_ms >= 0

    def test_captures_cost(self, cfg: LCLGConfig) -> None:
        with patch("lclg.agents.comparator.ChatAiGateway", side_effect=_mock_chat_ai_gateway):
            chain = build_comparator_chain(cfg)
            result = chain.invoke({"prompt": "test"})

        for pr in result.results:
            assert pr.cost_usd == "0.00050"

    def test_always_uses_explicit_mode(self, cfg: LCLGConfig) -> None:
        """ComparatorAgent uses ChatAiGateway regardless of LCLG_MODE."""
        proxy_cfg = LCLGConfig(
            gateway=cfg.gateway,
            mode="proxy-selfhosted",
            max_sub_questions=2,
            output_dir=cfg.output_dir,
        )
        with patch(
            "lclg.agents.comparator.ChatAiGateway", side_effect=_mock_chat_ai_gateway
        ) as mock_cls:
            chain = build_comparator_chain(proxy_cfg)
            chain.invoke({"prompt": "test"})
            # ChatAiGateway should have been called, not a proxy builder
            assert mock_cls.called
