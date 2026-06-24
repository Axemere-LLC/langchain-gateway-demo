"""Integration mode factories.

Each factory function returns a callable that builds a ChatAiGateway (or proxy-mode
LangChain chat model) for a given provider, model, and workload_id. The agents
call these factories; they don't know which mode is active.
"""

from .explicit_managed import build_explicit_managed
from .explicit_selfhosted import build_explicit_selfhosted
from .proxy_managed import build_proxy_managed
from .proxy_selfhosted import build_proxy_selfhosted

__all__ = [
    "build_explicit_managed",
    "build_explicit_selfhosted",
    "build_proxy_managed",
    "build_proxy_selfhosted",
]
