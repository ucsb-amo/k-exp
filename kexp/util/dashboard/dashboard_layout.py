"""Dashboard layout configuration.

Default placement (tab vs dock) and dock area for every panel id, plus
optional per-host overrides.

Layout strings
--------------
* ``placement``: ``"dock"`` (separate dock widget) or ``"tab"`` (tabified
  onto an existing dock in the same ``tab_group``)
* ``dock_area``: ``"left"`` / ``"right"`` / ``"top"`` / ``"bottom"``

The dashboard window prefers the user's saved QSettings layout; this
file's settings are used only as defaults the first time the dashboard
runs on a host (or after Reset Layout).
"""

from __future__ import annotations


# Server panel defaults.  Keys are server ids.
SERVER_PLACEMENT: dict[str, dict] = {
    # Each entry: placement + dock_area + optional tab_group.
    # Defaults: dock to the right, no tab group.
    "als":         {"placement": "dock", "dock_area": "left"},
    "precilaser":  {"placement": "dock", "dock_area": "left"},
    "monitor":     {"placement": "dock", "dock_area": "bottom"},
    "magnetometer":{"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "bristol":     {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "basler":      {"placement": "dock", "dock_area": "right"},
    "interlock":   {"placement": "dock", "dock_area": "top"},
}

# Client panel defaults.  Keys are client ids.
CLIENT_PLACEMENT: dict[str, dict] = {
    "data_browser":   {"placement": "dock", "dock_area": "left"},
    "monitor":        {"placement": "dock", "dock_area": "bottom"},
    "ethernet_relay": {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "remote_control": {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "keysight":       {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "interlock":      {"placement": "dock", "dock_area": "top"},
}

# Per-host overrides: same shape as SERVER_PLACEMENT / CLIENT_PLACEMENT, keyed
# by lab IP, merged on top of the defaults for that host.
HOST_LAYOUT_OVERRIDES: dict[str, dict[str, dict]] = {}
