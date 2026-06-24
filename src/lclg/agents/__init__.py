"""Agent factory functions.

Each agent exports build_<name>_chain(cfg: LCLGConfig) -> Runnable.
"""

from lclg.agents.analyst import build_analyst_chain
from lclg.agents.comparator import build_comparator_chain
from lclg.agents.planner import build_planner_chain
from lclg.agents.reporter import build_reporter_chain
from lclg.agents.researcher import build_researcher_chain

__all__ = [
    "build_planner_chain",
    "build_researcher_chain",
    "build_analyst_chain",
    "build_comparator_chain",
    "build_reporter_chain",
]
