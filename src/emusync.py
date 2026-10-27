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

# Make sure the project root and src/ are on the path when invoked directly
# (cli/ and server/ live under src/ after restructure)
_root = str(Path(__file__).parent)
if _root not in sys.path:
    sys.path.insert(0, _root)
_src = str(Path(__file__).parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from cli import cli

if __name__ == "__main__":
    cli()
