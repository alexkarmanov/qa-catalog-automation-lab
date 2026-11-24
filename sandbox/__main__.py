"""``python -m sandbox`` - run the synthetic sandbox for manual exploration (loopback only)."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading

from sandbox.seed import create_database
from sandbox.server import start_server


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sandbox", description=__doc__)
    parser.add_argument("--db", required=True, help="SQLite file; created from the synthetic seed if absent")
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 = random free port)")
    args = parser.parse_args(argv)
    if not os.path.exists(args.db):
        create_database(args.db)
    server = start_server(args.db, port=args.port)
    print("CAPS sandbox listening on %s (Ctrl+C to stop)" % server.url, flush=True)
    done = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: done.set())
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    try:
        done.wait()
    finally:
        server.stop()
        print("stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
