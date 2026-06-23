"""Headless launcher for BaslerCameraServer.

The dashboard spawns this as a subprocess; the embedded Basler panel is
a *client* (BaslerCamerasMainWindow) that discovers and connects to it
over ZMQ.

Usage::

    python -m kexp.util.guis.basler.basler_server_headless
"""
from __future__ import annotations

import argparse
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=int, default=0)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("basler_server_headless")

    from waxx.util.guis.basler.basler_camera_server import BaslerCameraServer

    try:
        server = BaslerCameraServer(instance_index=args.instance)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    log.info("starting BaslerCameraServer instance=%d", args.instance)
    try:
        server.start()  # blocks
    except KeyboardInterrupt:
        log.info("interrupted, stopping")
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
