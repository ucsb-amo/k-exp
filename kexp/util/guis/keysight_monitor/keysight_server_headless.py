"""Headless entry point for the Keysight current-supply server.

The IP/max-current list is experiment-specific and lives in kexp config.
The generic server implementation in waxx accepts whatever list we pass.
"""
from __future__ import annotations

from kexp.config.ip import KEYSIGHT_SUPPLIES
from waxx.util.guis.keysight.keysight_server import main as run_server


def main() -> None:
    run_server(supplies=KEYSIGHT_SUPPLIES)


if __name__ == "__main__":
    main()
