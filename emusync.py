#!/usr/bin/env python3
"""EmuSync CLI — save-file sync for emulators on a home LAN.

This is a thin entry-point shim. All subcommands live in the `cli/` package
(one module per command group). It is kept as `emusync.py` because external
callers invoke it by path — install.sh, the Makefile, the Electron main
process (`spawn`), and `pkill -f "emusync.py server start"`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure the project root is on the path when invoked directly
sys.path.insert(0, str(Path(__file__).parent))

from cli import cli

if __name__ == "__main__":
    cli()
