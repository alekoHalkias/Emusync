"""Root Click group. Command modules attach their subcommands onto `cli`."""
from __future__ import annotations

import click


@click.group()
def cli() -> None:
    """EmuSync — keep game saves in sync across your devices."""
