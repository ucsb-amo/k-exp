"""Dashboard layout configuration: the *default* placement of every panel.

Read by ``waxx.util.dashboard.host_config.load_layout_overrides(host_ip, kind)``
and applied by ``DashboardMainWindow`` the first time a dashboard runs on a
host, and again whenever the user picks ``Layout -> Reset to default layout``.
A layout the user has saved (QSettings, per host) always wins over this file.

Layout strings
--------------
* ``placement``: ``"dock"`` (its own dock, split from its neighbours in the
  same area) or ``"tab"`` (stacked with the other ``"tab"`` panels in the
  same area that share ``tab_group``)
* ``dock_area``: ``"left"`` / ``"right"`` / ``"top"`` / ``"bottom"``
* ``tab_group``: name of the tab stack (only for ``placement="tab"``)

Within one area, panels are laid out in the order the registry declares
them.  Side areas stack top-to-bottom; the top and bottom areas go
left-to-right.

Default server-dashboard picture::

    +-----------------------------------------------------------------+
    | Interlock                                                        |
    +-----------+------------------------------------+----------------+
    | ALS       |                                    | Basler         |
    +-----------+                                    +----------------+
    | Precilaser|                                    | diag: Magnet.. |
    |           |                                    |  | Bristol |Key|
    |           |                                    +----------------+
    |           |                                    | control: PDXC..|
    |           |                                    +----------------+
    |           |                                    | Running servers|
    +-----------+----------------------+-------------+----------------+
    | Device Control                   | Log                          |
    +----------------------------------+------------------------------+
"""

from __future__ import annotations


# Server panel defaults.  Keys are server ids (server_registry.py) plus the
# extra client panels the server dashboard shows and the framework panels
# ("_running_servers", "_log").
SERVER_PLACEMENT: dict[str, dict] = {
    "interlock":        {"placement": "dock", "dock_area": "top"},
    "als":              {"placement": "dock", "dock_area": "left"},
    "precilaser":       {"placement": "dock", "dock_area": "left"},
    "basler":           {"placement": "dock", "dock_area": "right"},
    "magnetometer":     {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "bristol":          {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "keysight":         {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "pdxc":             {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "tpi":              {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "remote_control":   {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "ethernet_relay":   {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "_running_servers": {"placement": "dock", "dock_area": "right"},
    "device_control":   {"placement": "dock", "dock_area": "bottom"},
    "_log":             {"placement": "dock", "dock_area": "bottom"},
}

# Client panel defaults.  Keys are client ids (client_registry.py).
CLIENT_PLACEMENT: dict[str, dict] = {
    "interlock":      {"placement": "dock", "dock_area": "top"},
    "als":            {"placement": "dock", "dock_area": "left"},
    "precilaser":     {"placement": "dock", "dock_area": "left"},
    "magnetometer":   {"placement": "dock", "dock_area": "left"},
    "basler":         {"placement": "dock", "dock_area": "right"},
    "bristol":        {"placement": "dock", "dock_area": "right"},
    "ethernet_relay": {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "remote_control": {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "keysight":       {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "tpi":            {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "device_control": {"placement": "dock", "dock_area": "bottom"},
    "_log":           {"placement": "dock", "dock_area": "bottom"},
}

# Per-host overrides: same shape as SERVER_PLACEMENT / CLIENT_PLACEMENT, keyed
# by lab IP, merged on top of the defaults for that host.
HOST_LAYOUT_OVERRIDES: dict[str, dict[str, dict]] = {}
