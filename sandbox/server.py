"""Start and stop the sandbox as a real HTTP server on a random loopback port."""
from __future__ import annotations

import http.client
import ipaddress
import logging
import os
import threading
from typing import Optional

from werkzeug.serving import BaseWSGIServer, make_server

from sandbox.app import create_app


class RunningServer:
    """Handle of a running sandbox server. ``stop()`` is idempotent and always releases the port."""

    def __init__(self, httpd: BaseWSGIServer, thread: threading.Thread, db_path: str, stop_event: threading.Event):
        self._httpd = httpd
        self._thread = thread
        self._stop_event = stop_event
        self.db_path = db_path
        self.host = httpd.host
        self.port = httpd.server_port
        self.stopped = False

    @property
    def url(self) -> str:
        return "http://%s:%d" % (self.host, self.port)

    def stop(self, timeout: float = 5.0) -> None:
        if self.stopped:
            return
        self.stopped = True
        self._stop_event.set()  # release handlers that are waiting (test-only slow route)
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise RuntimeError("sandbox server thread did not stop within %.1f s" % timeout)

    def __enter__(self) -> "RunningServer":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def _require_loopback(host: str) -> None:
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ValueError("the sandbox binds to loopback addresses only, got %r" % host)


def start_server(
    db_path: str,
    test_routes: bool = False,
    host: str = "127.0.0.1",
    port: int = 0,
    ready_timeout: float = 5.0,
) -> RunningServer:
    """Serve ``db_path`` on ``host:port`` (port 0 = random free port) and wait until it answers."""
    _require_loopback(host)
    if not os.path.isfile(db_path):
        raise FileNotFoundError("database file not found: %s" % os.path.basename(db_path))
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # keep test output readable
    app = create_app(db_path, test_routes=test_routes)
    try:
        httpd = make_server(host, port, app, threaded=True)
    except SystemExit as exc:  # werkzeug calls sys.exit(1) when the port is taken; surface it as a normal error
        raise OSError("could not bind %s:%d (address in use?)" % (host, port)) from exc
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), name="caps-sandbox", daemon=True)
    server = RunningServer(httpd, thread, db_path, app.config["STOP_EVENT"])
    thread.start()
    try:
        _wait_until_ready(server, ready_timeout)
    except BaseException:
        server.stop()
        raise
    return server


def _wait_until_ready(server: RunningServer, timeout: float) -> None:
    # The listening socket already exists, so one bounded request is the readiness check (no polling loop, no sleep).
    conn: Optional[http.client.HTTPConnection] = None
    try:
        conn = http.client.HTTPConnection(server.host, server.port, timeout=timeout)
        conn.request("GET", "/api/v1/health")
        resp = conn.getresponse()
        resp.read()
        if resp.status != 200:
            raise RuntimeError("sandbox health check returned HTTP %d" % resp.status)
    finally:
        if conn is not None:
            conn.close()
