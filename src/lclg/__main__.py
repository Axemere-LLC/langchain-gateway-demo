"""LCLG CLI entry point.

Usage:
  python -m lclg --topic "solid state battery materials 2026"
  LCLG_MODE=proxy-managed python -m lclg --topic "..."
  python -m lclg --render-only   # re-render the last cached report
"""

from __future__ import annotations

import sys

import click

# Load .env before Click reads envvar defaults or any code reads os.environ.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from lclg.config import LCLGConfig


@click.command()
@click.option("--topic", "-t", envvar="LCLG_TOPIC", default="", help="Research topic")
@click.option(
    "--mode",
    envvar="LCLG_MODE",
    default=None,
    help="Integration mode (overrides LCLG_MODE env var)",
)
@click.option(
    "--output-dir",
    envvar="LCLG_OUTPUT_DIR",
    default=None,
    help="Output directory for reports (default: ./output)",
)
@click.option(
    "--render-only",
    is_flag=True,
    default=False,
    help="Re-render the most recent cached report without running the pipeline",
)
def cli(topic: str, mode: str | None, output_dir: str | None, render_only: bool) -> None:
    """LCLG — LangChain + Axemere Gateway multi-agent research pipeline.

    Routes every LLM call through the Axemere gateway for attribution,
    cost tracking, and policy enforcement. No provider API keys required locally.

    \b
    Environment variables:
      LCLG_MODE               explicit-managed | explicit-selfhosted | proxy-managed | proxy-selfhosted
      AXEMERE_GATEWAY_TOKEN   Axemere gateway token (managed modes)
      AXEMERE_PROJECT_ID      Attribution project ID
      AXEMERE_GATEWAY_URL     Override gateway URL (default: https://us.gw.axemere.ai)
      TAVILY_API_KEY          Optional web search for ResearchAgent
      LCLG_TOPIC              Research topic (alternative to --topic)
      LCLG_OUTPUT_DIR         Output directory (default: ./output)

    \b
    See docs/prerequisites.md for full setup instructions.
    """
    from lclg.report.builder import build_report, load_latest_result

    if render_only:
        cfg = LCLGConfig.from_env()
        if output_dir:
            cfg.output_dir = output_dir

        result = load_latest_result(cfg.output_dir)
        if result is None:
            click.echo("No cached pipeline result found. Run without --render-only first.")
            sys.exit(1)

        paths = build_report(result, cfg.output_dir)
        click.echo("Report re-rendered:")
        for fmt, path in paths.items():
            click.echo(f"  {fmt}: {path}")
        return

    # Normal pipeline run
    cfg = LCLGConfig.from_env()
    if mode:
        cfg.mode = mode
    if output_dir:
        cfg.output_dir = output_dir

    if not topic:
        topic = click.prompt("Research topic")

    if not topic:
        click.echo("Error: --topic is required", err=True)
        sys.exit(1)

    # Validate managed mode has a gateway token
    if cfg.is_managed and not cfg.gateway.gateway_token:
        click.echo(
            "Error: AXEMERE_GATEWAY_TOKEN is required for managed gateway modes.\n"
            "Set it in .env or use a self-hosted mode (LCLG_MODE=explicit-selfhosted).",
            err=True,
        )
        sys.exit(1)

    click.echo(f"LCLG — mode={cfg.mode}, topic={topic!r}")
    click.echo(f"Gateway: {cfg.gateway.gateway_url}")
    if cfg.tavily_api_key:
        click.echo("Web search: enabled (Tavily)")
    else:
        click.echo("Web search: disabled (model knowledge fallback)")
    click.echo()

    from lclg.pipeline import run_pipeline

    try:
        result = run_pipeline(topic, cfg)
    except Exception as exc:
        # Surface full gateway denial trace so configuration problems are diagnosable.
        _handle_pipeline_error(exc)
        sys.exit(1)

    paths = build_report(result, cfg.output_dir)

    click.echo("\nReports written:")
    for fmt, path in paths.items():
        click.echo(f"  {fmt}: {path}")


def _handle_pipeline_error(exc: Exception) -> None:
    """Print a human-readable error for gateway failures."""
    try:
        from axemere.gateway import GatewayError, PolicyDeniedError

        if isinstance(exc, PolicyDeniedError):
            click.echo(f"\nGateway denied the request: {exc}", err=True)
            return
        if isinstance(exc, GatewayError):
            click.echo(f"\nGateway error: {exc}", err=True)
            return
    except ImportError:
        pass
    raise


if __name__ == "__main__":
    cli()
