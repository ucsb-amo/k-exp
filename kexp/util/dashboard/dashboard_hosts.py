"""Per-host autostart configuration for the dashboards.

Keys are the lab-subnet IP of each lab PC (192.168.1.x).  Values are lists
of server ids (matching :data:`SERVER_SPECS` in ``server_registry.py``)
that the server dashboard should auto-start when launched on that host.

Hosts not listed here get an empty autostart set (every server is
manually startable from the dashboard regardless).

To add a host: find its lab IP with ``ipconfig`` on Windows, look for the
``192.168.1.x`` entry, and add an entry below.
"""

from __future__ import annotations


# Map: lab-subnet IP -> list of server ids that should autostart on that PC.
#
# Server ids are the canonical short names declared in server_registry.py
# (e.g. "als", "precilaser", "monitor", "magnetometer", "bristol", "basler",
# "interlock").
HOST_AUTOSTART_SERVERS: dict[str, list[str]] = {
    # Lab control PC - runs every hardware-owning server.
    "*": [
        "basler",
    ],
    "192.168.1.76": [
        "als",
        "precilaser",
        "monitor",
        "magnetometer",
        "bristol",
        "basler",
        "keysight",
        "interlock",
        "pdxc",
        "tpi",
    ],
    "192.168.1.79": [
        "monitor"
    ]
}
