"""Shared test fixtures for LCLG tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from axemere.gateway import AiGatewayConfig
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from lclg.config import LCLGConfig


@pytest.fixture
def mock_gateway_cfg() -> AiGatewayConfig:
    return AiGatewayConfig(
        gateway_url="http://localhost:7080",
        gateway_token=None,
        workload_id="wl_lclg_test",
        project_id="prj_test",
        customer_id="",
        account_id="",
    )


@pytest.fixture
def cfg(mock_gateway_cfg: AiGatewayConfig) -> LCLGConfig:
    return LCLGConfig(
        gateway=mock_gateway_cfg,
        mode="explicit-selfhosted",
        max_sub_questions=2,
        output_dir="/tmp/lclg_test_output",
        tavily_api_key=None,
    )


@pytest.fixture
def cfg_with_tavily(mock_gateway_cfg: AiGatewayConfig) -> LCLGConfig:
    return LCLGConfig(
        gateway=mock_gateway_cfg,
        mode="explicit-selfhosted",
        max_sub_questions=2,
        output_dir="/tmp/lclg_test_output",
        tavily_api_key="tvly-test-key",
    )


def make_runnable_llm(content: str = "test response") -> RunnableLambda:
    """Return a RunnableLambda that behaves like an LLM in LCEL chains.

    A plain MagicMock breaks LCEL piping because LangChain wraps non-Runnables
    as RunnableLambda callables, calling mock() instead of mock.invoke().
    """
    return RunnableLambda(lambda _: AIMessage(content=content))


def make_mock_chat_ai_gateway(content: str = "test response") -> MagicMock:
    """Return a MagicMock for ChatAiGateway whose _generate() returns a valid ChatResult.

    Used in comparator tests where _generate() is called directly (not via LCEL pipe).
    """
    mock = MagicMock()
    mock._generate.return_value = ChatResult(
        generations=[
            ChatGeneration(
                message=AIMessage(content=content),
                generation_info={
                    "record_id": "rec-test-001",
                    "metering": {
                        "cost_usd": "0.00010",
                        "tokens_in": 50,
                        "tokens_out": 100,
                    },
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                },
            )
        ]
    )
    return mock
