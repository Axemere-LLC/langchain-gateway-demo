"""LCLG configuration: wraps AiGatewayConfig with pipeline-specific settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from axemere.gateway import AiGatewayConfig

# [AXEMERE] Workload IDs — one per agent for per-agent cost attribution
# Each constant maps to a workload registered in the Axemere console (managed)
# or gateway config (self-hosted). Using separate workload IDs means the console
# shows individual cost and usage lines for each agent, not a single total.
# Alternatives:
#   A) Single workload for the whole pipeline — simpler setup, but loses
#      per-agent visibility. Useful for quick prototypes.
#   B) Dynamic workload IDs per run — possible, but workloads need to be
#      pre-registered; dynamic IDs that don't match a workload will be rejected.
# Docs: https://axemere.ai/docs/guides/configuration/workloads
WORKLOAD_PLANNER = "wl_lclg_planner"
WORKLOAD_RESEARCHER = "wl_lclg_researcher"
WORKLOAD_ANALYST = "wl_lclg_analyst"
WORKLOAD_COMPARATOR = "wl_lclg_comparator"
WORKLOAD_REPORTER = "wl_lclg_reporter"

VALID_MODES = frozenset(
    ["explicit-managed", "explicit-selfhosted", "proxy-managed", "proxy-selfhosted"]
)


@dataclass
class LCLGConfig:
    """Runtime configuration for the LCLG pipeline."""

    gateway: AiGatewayConfig
    mode: str = "explicit-managed"
    max_sub_questions: int = 4
    output_dir: str = "./output"
    tavily_api_key: str | None = None
    # Set by run_pipeline() so every gateway call carries a run_id label,
    # making it easy to filter all records belonging to one pipeline run.
    run_id: str | None = None

    # Optional admin token for the self-hosted / Docker gateway.
    # When set, the pipeline fetches full gateway metering (tokens, cost, provider)
    # for streaming agents (analyst, reporter) where llm_output=None.
    # For managed gateway runs, leave unset — the token is not available to users.
    admin_token: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"Invalid LCLG_MODE {self.mode!r}. Valid values: {sorted(VALID_MODES)}"
            )

    @classmethod
    def from_env(cls) -> LCLGConfig:
        """Load configuration from environment variables / .env file."""
        # AiGatewayConfig.from_env() reads all AXEMERE_* variables.
        # load_dotenv() should be called by the caller (e.g. __main__.py) before this.
        gateway = AiGatewayConfig.from_env()

        mode = os.environ.get("LCLG_MODE", "explicit-managed")
        max_sq = int(os.environ.get("LCLG_MAX_SUB_QUESTIONS", "4"))
        output_dir = os.environ.get("LCLG_OUTPUT_DIR", "./output")
        tavily_key = os.environ.get("TAVILY_API_KEY") or None
        admin_token = os.environ.get("MVGC_ADMIN_TOKEN") or None

        return cls(
            gateway=gateway,
            mode=mode,
            max_sub_questions=max(1, min(max_sq, 10)),
            output_dir=output_dir,
            tavily_api_key=tavily_key,
            admin_token=admin_token,
        )

    @property
    def is_managed(self) -> bool:
        """True for modes that use the Axemere managed cloud gateway."""
        return self.mode.endswith("-managed")

    @property
    def is_explicit(self) -> bool:
        """True for modes that use ChatAiGateway (POST /v1/actions:execute)."""
        return self.mode.startswith("explicit-")

    @property
    def is_proxy(self) -> bool:
        """True for modes that route native LangChain providers through the gateway proxy."""
        return self.mode.startswith("proxy-")
