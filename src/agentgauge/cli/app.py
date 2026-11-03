"""The ``agentgauge`` command line interface."""

from __future__ import annotations

from typing import Annotated

import typer

from agentgauge import __version__

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
