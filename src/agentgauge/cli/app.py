"""The ``agentgauge`` command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import anyio
import typer
from pydantic import ValidationError
from rich.console import Console

from agentgauge import __version__
from agentgauge.calibration import LabelLoadError, load_labels
from agentgauge.calibration import calibrate as compute_calibration
from agentgauge.cli.render import render_calibration, render_run, render_run_list
from agentgauge.core import ProviderConfig, RunResult, Suite, SuiteLoadError, load_suite
from agentgauge.judge import Scale
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


@app.command()
def calibrate(
    suite_path: Annotated[
        Path, typer.Argument(metavar="SUITE", help="Suite file (.yaml, .yml or .jsonl).")
    ],
    labels_path: Annotated[
        Path, typer.Option("--labels", help="Human labels file (.yaml, .yml or .jsonl).")
    ],
    scorer: Annotated[
        str, typer.Option(help="Name of the judge scorer in the suite.")
    ] = "llm_judge",
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
    """Measure how well SUITE's judge agrees with human labels.

    Runs the model under test and the judge scorer on the labelled cases, then
    compares the judge's scores with the labels: accuracy, Cohen's kappa with a
    95% bootstrap interval, a confusion matrix and per-class precision and
    recall. Warns when kappa is below 0.6. Nothing is stored in the run
    database; judge replies are cached, so repeating this is free.

    Exits 2 on configuration problems (bad suite or labels, labels for unknown
    cases or off the scale, no such scorer) and 1 when no labelled case could be
    judged. A low kappa is a warning, not a failure.
    """
    try:
        suite = load_suite(suite_path)
        labels = {label.case_id: label for label in load_labels(labels_path)}
        config = _resolve_provider(suite.provider, provider_type, model, base_url, api_key_env)
    except (SuiteLoadError, LabelLoadError) as exc:
        _fail(str(exc))
    specs = tuple(spec for spec in suite.scorers if spec.name == scorer)
    if len(specs) != 1:
        found = "no" if not specs else "more than one"
        _fail(f"suite {suite.name!r} has {found} scorer named {scorer!r}; calibrate needs one")
    known = {case.id for case in suite.cases}
    unknown = sorted(set(labels) - known)
    if unknown:
        _fail(f"labels refer to cases that are not in the suite: {', '.join(unknown)}")
    labelled = suite.model_copy(
        update={
            "scorers": specs,
            "cases": tuple(case for case in suite.cases if case.id in labels),
        }
    )
    try:
        result = anyio.run(_execute, labelled, config, concurrency)
    except (ScorerConfigError, ProviderConfigError) as exc:
        _fail(str(exc))

    human: list[int] = []
    judged: list[int] = []
    skipped: list[str] = []
    scale: Scale | None = None
    judge_model = result.model
    for case in result.results:
        score = next((s for s in case.scores if s.scorer == scorer), None)
        if case.error is not None or score is None:
            skipped.append(case.case_id)
            continue
        raw_scale = score.details.get("scale")
        if raw_scale is None:
            _fail(f"scorer {scorer!r} does not report a scale; calibrate needs an LLM judge")
        scale = Scale.model_validate(raw_scale)
        judge_model = str(score.details.get("judge_model", judge_model))
        human.append(labels[case.case_id].label)
        judged.append(round(score.value))
    if scale is None:
        _fail("no labelled case could be judged; nothing to compare", code=1)
    off_scale = sorted(
        case_id
        for case_id, label in labels.items()
        if case_id not in skipped and label.label not in scale.values
    )
    if off_scale:
        _fail(f"labels outside the judge's scale {list(scale.values)} for: {', '.join(off_scale)}")
    report = compute_calibration(human, judged, scale)
    render_calibration(
        Console(),
        report,
        suite_name=suite.name,
        judge_model=judge_model,
        skipped=skipped,
        unlabelled=len(suite.cases) - len(labels),
    )
