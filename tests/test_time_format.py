"""Unit tests for the CLI human-readable timestamp helpers (issue #216).

Pure functions — no server needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cli.common import _fmt_time, _parse_iso_utc, _relative

NOW = datetime(2026, 6, 16, 21, 25, 0, tzinfo=timezone.utc)


# ── _parse_iso_utc ──────────────────────────────────────────────────────────────

def test_parse_iso_with_offset():
    assert _parse_iso_utc("2026-06-16T21:25:00+00:00") == NOW


def test_parse_iso_naive_assumed_utc():
    # No tz designator → treated as UTC, not local.
    assert _parse_iso_utc("2026-06-16T21:25:00") == NOW


def test_parse_iso_none_and_bad():
    assert _parse_iso_utc(None) is None
    assert _parse_iso_utc("") is None
    assert _parse_iso_utc("not-a-date") is None


# ── _relative ───────────────────────────────────────────────────────────────────

def test_relative_just_now():
    assert _relative(NOW - timedelta(seconds=10), NOW) == "just now"


def test_relative_minutes():
    assert _relative(NOW - timedelta(minutes=5), NOW) == "5 minutes ago"


def test_relative_singular_hour():
    assert _relative(NOW - timedelta(hours=1), NOW) == "1 hour ago"


def test_relative_hours():
    assert _relative(NOW - timedelta(hours=2), NOW) == "2 hours ago"


def test_relative_days():
    assert _relative(NOW - timedelta(days=3), NOW) == "3 days ago"


def test_relative_future():
    assert _relative(NOW + timedelta(minutes=10), NOW) == "in 10 minutes"


# ── _fmt_time ───────────────────────────────────────────────────────────────────

def test_fmt_time_combines_relative_and_exact():
    # A timestamp well in the past renders "<relative> (<exact local 12h>)".
    iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    out = _fmt_time(iso)
    assert "ago" in out
    assert out.endswith(")") and "(" in out
    # 12-hour clock → an AM/PM marker is present in the exact portion.
    assert "AM" in out or "PM" in out


def test_fmt_time_bad_value_falls_back():
    assert _fmt_time(None) == "?"
    assert _fmt_time("garbage") == "garbage"
