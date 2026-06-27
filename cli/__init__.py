"""EmuSync CLI package.

The root Click group lives in `cli.root`. Importing this package pulls in every
command module so their `@cli.*` decorators register subcommands onto the group.
"""
from cli.root import cli

# Import for side effects: each module attaches its commands to `cli`.
from cli import console  # noqa: E402,F401
from cli import device  # noqa: E402,F401
from cli import game  # noqa: E402,F401
from cli import rom  # noqa: E402,F401
from cli import run  # noqa: E402,F401
from cli import server  # noqa: E402,F401
from cli import sync  # noqa: E402,F401
from cli import transfer  # noqa: E402,F401

__all__ = ["cli"]
