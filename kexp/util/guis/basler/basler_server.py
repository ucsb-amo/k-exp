"""kexp launcher for BaslerCameraServer.

Starts the server for all Basler cameras connected to this machine.
Discovered automatically by any client running ``discover_all_basler_cameras()``.

Usage::

    python basler_server.py              # instance 0 (normal)
    python basler_server.py --instance 1 # if two servers must co-exist on one host

The server runs until interrupted (Ctrl-C or process kill).
"""
import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

from waxx.util.guis.basler.basler_camera_server import BaslerCameraServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Basler camera server")
    parser.add_argument(
        "--instance",
        type=int,
        default=0,
        help="Instance index (0 for the normal single-server case)",
    )
    args = parser.parse_args()

    server = BaslerCameraServer(instance_index=args.instance)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
