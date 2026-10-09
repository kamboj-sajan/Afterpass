"""AfterPass command-line interface."""

from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _todo(phase: int) -> None:
    typer.echo(f"Not implemented yet (Phase {phase}).")
    raise typer.Exit(1)


@app.command()
def replay(season: int = 2025, districts: str = "Sangrur,Bathinda,Firozpur") -> None:
    """Process a full past season."""
    _todo(2)


@app.command()
def live() -> None:
    """Process the current season up to today."""
    _todo(6)


@app.command()
def smoke() -> None:
    """Run the 48-hour smoke forecast."""
    _todo(4)


@app.command()
def imagery(top: int = 20) -> None:
    """Render before/after crops for the top villages."""
    _todo(2)


@app.command()
def validate() -> None:
    """Compute validation metrics."""
    _todo(2)


@app.command()
def publish(target: str = "local") -> None:
    """Publish data-contract files to data/public or S3."""
    _todo(2)


if __name__ == "__main__":
    app()
