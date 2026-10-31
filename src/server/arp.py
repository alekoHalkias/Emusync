"""Resolve a LAN client's MAC from the OS neighbor table (#656).

ARP only lists on-link neighbors, so a routed client never yields the gateway
MAC; anything unresolvable returns None and callers keep UUID-only behavior.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ARP_PATH = Path("/proc/net/arp")  # test seam; `arp -a` is used when absent
_MAC_RE = re.compile(r"\b([0-9a-f]{1,2}(?:[:-][0-9a-f]{1,2}){5})\b", re.I)


def _norm(raw: str) -> str | None:
    mac = ":".join(p.zfill(2) for p in re.split(r"[:-]", raw.lower()))
    return None if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff") else mac


def mac_for_ip(ip: str) -> str | None:
    try:
        if _ARP_PATH.exists():
            text = _ARP_PATH.read_text()
        else:
            text = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in text.splitlines():
        if re.search(rf"(?<![\d.]){re.escape(ip)}(?![\d.])", line):
            m = _MAC_RE.search(line)
            if m:
                return _norm(m.group(1))
    return None
