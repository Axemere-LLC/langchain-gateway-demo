"""Build HTML and Markdown reports from a PipelineResult."""

from __future__ import annotations

import json
from pathlib import Path

from lclg.pipeline import PipelineResult
from lclg.report.html import render_html
from lclg.report.markdown import render_markdown


def build_report(result: PipelineResult, output_dir: str = "./output") -> dict[str, Path]:
    """Write HTML, Markdown, and JSON cache to output/<run_id>/.

    Returns a dict mapping format names to the written file paths.
    """
    run_dir = Path(output_dir) / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    # JSON cache — used by `make report` to re-render without LLM calls
    json_path = run_dir / "pipeline_result.json"
    json_path.write_text(_to_json(result), encoding="utf-8")
    paths["json"] = json_path

    # HTML report — primary artifact
    html_path = run_dir / "report.html"
    html_path.write_text(render_html(result), encoding="utf-8")
    paths["html"] = html_path

    # Markdown report — GitHub-friendly
    md_path = run_dir / "report.md"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    paths["markdown"] = md_path

    return paths


def load_latest_result(output_dir: str = "./output") -> PipelineResult | None:
    """Load the most recently written PipelineResult from the cache."""
    base = Path(output_dir)
    if not base.exists():
        return None

    json_files = sorted(base.glob("*/pipeline_result.json"), key=lambda p: p.stat().st_mtime)
    if not json_files:
        return None

    return _from_json(json_files[-1].read_text(encoding="utf-8"))


def _to_json(result: PipelineResult) -> str:
    import dataclasses

    return json.dumps(dataclasses.asdict(result), indent=2, default=str)


def _from_json(text: str) -> PipelineResult:
    from lclg.agents.comparator import ComparatorResult, ProviderResult
    from lclg.agents.researcher import ResearchResult
    from lclg.pipeline import AgentCall, PipelineResult

    data = json.loads(text)

    data["research"] = [ResearchResult(**r) for r in data.get("research", [])]
    data["calls"] = [AgentCall(**c) for c in data.get("calls", [])]

    if data.get("comparison"):
        cmp = data["comparison"]
        cmp["results"] = [ProviderResult(**r) for r in cmp.get("results", [])]
        data["comparison"] = ComparatorResult(**cmp)
    else:
        data["comparison"] = None

    return PipelineResult(**data)
