"""Regression test for issue #458: a single missed /health window must not be
fatal to `emusync run`'s reachability check — SyncClient.health(retries=N)
should retry before conceding the server is offline.

Real HTTP against a local socket (no mocking): the first N-1 requests get
connection-refused (nothing listening yet), then a real http.server starts
answering 200 for the rest.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from server.sync_client import SyncClient


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_):
        pass  # quiet


def test_health_retries_past_a_transient_failure():
    # Reserve a port that's closed at first (nothing bound yet), so an
    # immediate health() call fails exactly like a transient connection blip.
    port = 18765
    client = SyncClient("127.0.0.1", port, pin="", device_id="d", device_name="t")

    server = HTTPServer(("127.0.0.1", port + 0), _HealthHandler)
    # Don't serve yet — start the listener slightly late, after the first
    # health() attempt would already have failed, to prove the retry recovers.
    def _start_late():
        time.sleep(0.3)
        server.serve_forever()

    # health() with no retries must fail while nothing is listening.
    assert client.health(retries=0) is False

    t = threading.Thread(target=_start_late, daemon=True)
    t.start()
    try:
        # health() with retries should succeed once the late listener comes up.
        assert client.health(retries=3, retry_delay=0.3) is True
    finally:
        server.shutdown()
        t.join(timeout=2)
    client.close()


if __name__ == "__main__":
    test_health_retries_past_a_transient_failure()
    print("ok")
