"""Regression test (issue #458 follow-up): the lock heartbeat cadence must
stay comfortably under the server's presence offline timeout.

A headless `emusync run` session (Steam Deck Gaming Mode, no GUI /whoami
heartbeat) has only this heartbeat keeping the device "online" server-side —
if it's slower than the server's timeout, any long session gets marked
offline mid-game and has its lock force-released out from under it.
"""
from cli.run import _HEARTBEAT_INTERVAL_SECONDS
from server.api._core import OFFLINE_TIMEOUT_SECONDS


def test_heartbeat_interval_stays_under_presence_offline_timeout():
    # Leave real margin for the server's 30s poll granularity + network delay,
    # not just squeak in under the wire.
    assert _HEARTBEAT_INTERVAL_SECONDS <= OFFLINE_TIMEOUT_SECONDS - 60


if __name__ == "__main__":
    test_heartbeat_interval_stays_under_presence_offline_timeout()
    print("ok")
