"""The ``agentgauge`` command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import anyio
import typer
from pydantic import ValidationError
from rich.console import Console

from agentgauge import __version__
from agentgauge.cli.render import render_run, render_run_list
from agentgauge.core import ProviderConfig, RunResult, Suite, SuiteLoadError, load_suite
from agentgauge.providers import ProviderConfigError, build_provider
from agentgauge.runner import run_suite
from agentgauge.scorers import ScorerConfigError
from agentgauge.storage import RunStore, StorageError

DEFAULT_DB = Path(".agentgauge/runs.db")
CONFIG_ERROR = 2

app = typer.Typer(
    name="agentgauge",
    help="Regression testing for LLM agents.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"agentgauge {__version__}")
        raise typer.Exit()


runs_app = typer.Typer(help="Inspect stored runs.", no_args_is_help=True)
app.add_typer(runs_app, name="runs")

DbOption = Annotated[Path, typer.Option("--db", envvar="AGENTGAUGE_DB", help="Run database file.")]


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_print_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """Regression testing for LLM agents."""


def _fail(message: str, code: int = CONFIG_ERROR) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def _resolve_provider(
    configured: ProviderConfig | None,
    provider_type: str | None,
    model: str | None,
    base_url: str | None,
    api_key_env: str | None,
) -> ProviderConfig:
    """Layer command-line options over the suite's provider block."""
    options = {
        "type": provider_type,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
    }
    updates = {key: value for key, value in options.items() if value is not None}
    merged = {**(configured.model_dump() if configured else {}), **updates}
    if "type" not in merged:
        if model is None:
            _fail(
                "no provider configured: add a 'provider' block to the suite, "
                "or pass --model (and --provider fake for the fake provider)"
            )
        merged["type"] = "openai_compat"
    try:
        return ProviderConfig.model_validate(merged)
    except ValidationError as exc:
        _fail(f"invalid provider options: {exc.errors()[0]['msg']}")


async def _execute(suite: Suite, config: ProviderConfig, concurrency: int) -> RunResult:
    provider = build_provider(config)
    try:
        return await run_suite(suite, provider, concurrency=concurrency)
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()


@app.command()
def run(
    suite_path: Annotated[
        Path, typer.Argument(metavar="SUITE", help="Suite file (.yaml, .yml or .jsonl).")
    ],
    db: DbOption = DEFAULT_DB,
    provider_type: Annotated[
        str | None,
        typer.Option("--provider", help="Provider type: openai_compat or fake."),
    ] = None,
    model: Annotated[str | None, typer.Option(help="Model name; overrides the suite.")] = None,
    base_url: Annotated[
        str | None, typer.Option(help="OpenAI-compatible endpoint; overrides the suite.")
    ] = None,
    api_key_env: Annotated[
        str | None, typer.Option(help="Environment variable holding the API key.")
    ] = None,
    concurrency: Annotated[int, typer.Option(min=1, help="Maximum cases in flight at once.")] = 8,
) -> None:
    """Run SUITE against a model, score the outputs and store the run.

    Exits 2 on configuration problems (bad suite, scorer or provider options,
    unusable database). Cases that fail scoring or error do not change the exit
    code; they are reported in the results table.
    """
    try:
        suite = load_suite(suite_path)
        config = _resolve_provider(suite.provider, provider_type, model, base_url, api_key_env)
        store = RunStore(db)
    except (SuiteLoadError, StorageError) as exc:
        _fail(str(exc))
    with store:
        try:
            result = anyio.run(_execute, suite, config, concurrency)
        except (ScorerConfigError, ProviderConfigError) as exc:
            _fail(str(exc))
        store.save_run(result)
    console = Console()
    render_run(console, result)
    console.print(f"Stored as run {result.run_id[:8]} in {db}")


@runs_app.command("list")
def runs_list(
    db: DbOption = DEFAULT_DB,
    limit: Annotated[int, typer.Option(min=1, help="Show at most this many runs.")] = 20,
) -> None:
    """List stored runs, newest first."""
    try:
        with RunStore(db) as store:
            summaries = store.list_runs(limit=limit)
    except StorageError as exc:
        _fail(str(exc))
    render_run_list(Console(), summaries)


@runs_app.command("show")
def runs_show(
    run_id: Annotated[str, typer.Argument(metavar="ID", help="Run id or unique id prefix.")],
    db: DbOption = DEFAULT_DB,
) -> None:
    """Show one stored run in detail, including each case's output."""
    try:
        store = RunStore(db)
    except StorageError as exc:
        _fail(str(exc))
    with store:
        try:
            run = store.get_run(run_id)
        except StorageError as exc:  # unknown id or ambiguous prefix
            _fail(str(exc), code=1)
    render_run(Console(), run, verbose=True)
