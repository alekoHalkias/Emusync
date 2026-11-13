"""Import wizard no-emulator state (issue #744).

Every console suggestion must map to a download link in EmulatorStep.tsx, and
every seeded core lib must be safe to drop into the buildbot URL that
installCore.ts builds (it also validates renderer input against these libs).
"""
from __future__ import annotations

import re
from pathlib import Path

from cli.consoles_data import _IMPORT_CONSOLES, _IMPORT_SYSTEMS

_STEP_TSX = (Path(__file__).parent.parent / "gui" / "renderer" / "src" / "components"
             / "console-import" / "EmulatorStep.tsx")


def _link_keys() -> set[str]:
    src = _STEP_TSX.read_text()
    table = re.search(r"SUGGESTION_LINKS[^{]*\{(.*?)\};", src, re.S)
    assert table, "SUGGESTION_LINKS table not found in EmulatorStep.tsx"
    return set(re.findall(r"^\s*(\w+):\s*\"https://", table.group(1), re.M))


def test_suggestion_links_cover_all_suggestions():
    keys = _link_keys()
    missing = sorted({s for c in _IMPORT_CONSOLES for s in c.get("suggestions", [])
                      if s.split(" ")[0] not in keys})
    assert not missing, f"add a SUGGESTION_LINKS entry for: {missing}"


def test_core_libs_are_buildbot_safe():
    bad = sorted({core["lib"] for sys in _IMPORT_SYSTEMS.values() for core in sys.get("cores", [])
                  if not re.fullmatch(r"[a-z0-9_-]+_libretro", core["lib"])})
    assert not bad, f"core libs not matching buildbot naming: {bad}"
