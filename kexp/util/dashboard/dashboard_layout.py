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
    | bottom: Monitor | Log            | Device Control               |
    +----------------------------------+------------------------------+

(Monitor -- the monitor server's run queue and state -- and Log share one tab
stack; the stack sits where its first panel, Monitor, is declared: before
Device Control.)
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
    "raman_fp_lock":    {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "keysight":         {"placement": "tab",  "dock_area": "right", "tab_group": "diag"},
    "pdxc":             {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "tpi":              {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "remote_control":   {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "ethernet_relay":   {"placement": "tab",  "dock_area": "right", "tab_group": "control"},
    "_running_servers": {"placement": "dock", "dock_area": "right"},
    "monitor":          {"placement": "tab",  "dock_area": "bottom", "tab_group": "bottom"},
    "device_control":   {"placement": "dock", "dock_area": "bottom"},
    "_log":             {"placement": "tab",  "dock_area": "bottom", "tab_group": "bottom"},
}

# Client panel defaults.  Keys are client ids (client_registry.py).
CLIENT_PLACEMENT: dict[str, dict] = {
    "interlock":      {"placement": "dock", "dock_area": "top"},
    "als":            {"placement": "dock", "dock_area": "left"},
    "precilaser":     {"placement": "dock", "dock_area": "left"},
    "magnetometer":   {"placement": "dock", "dock_area": "left"},
    "basler":         {"placement": "dock", "dock_area": "right"},
    "bristol":        {"placement": "dock", "dock_area": "right"},
    "raman_fp_lock":  {"placement": "tab",  "dock_area": "right", "tab_group": "lock"},
    "diagnostic_viewer": {"placement": "dock", "dock_area": "right"},
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

# Layout -> Auto-arrange (waxx.util.dashboard.layout_solver): what each panel
# is worth on screen and the size it needs, for both dashboards.
#   tier:   "primary"  -- always on screen; spare space goes here first
#           "frequent" -- on screen when it fits
#           "status"   -- status readouts, glanced at: may sit behind a tab
#           "rare"     -- the first to be stacked
#   family: panels of one family prefer to share a tab stack
#   min / pref: (w, h) px of the whole dock, header included.  Estimates; the
#           dashboard also measures every built panel and never goes below
#           the minimum Qt reports for it.
#   areas:  optional, the dock areas the panel may go in
# Preview without a dashboard:
#   python -m waxx.util.dashboard.layout_solver --layout-module kexp.util.dashboard.dashboard_layout --display 1920x1080
AUTO_LAYOUT_HINTS: dict[str, dict] = {
    "device_control":    {"tier": "primary",  "family": "run",       "min": (1100, 560), "pref": (1600, 680)},
    "basler":            {"tier": "primary",  "family": "camera",    "min": (640, 480),  "pref": (1000, 760)},
    "monitor":           {"tier": "primary",  "family": "run",       "min": (700, 260),  "pref": (1100, 420)},
    "interlock":         {"tier": "frequent", "family": "interlock", "min": (600, 160),  "pref": (1400, 240)},
    "als":               {"tier": "frequent", "family": "lasers",    "min": (320, 360),  "pref": (380, 480)},
    "precilaser":        {"tier": "frequent", "family": "lasers",    "min": (320, 360),  "pref": (380, 480)},
    "diagnostic_viewer": {"tier": "frequent", "family": "camera",    "min": (500, 400),  "pref": (900, 600)},
    "magnetometer":      {"tier": "status",   "family": "diag",      "min": (360, 240),  "pref": (600, 360)},
    "bristol":           {"tier": "status",   "family": "diag",      "min": (360, 240),  "pref": (600, 360)},
    "keysight":          {"tier": "status",   "family": "diag",      "min": (400, 260),  "pref": (700, 380)},
    "raman_fp_lock":     {"tier": "status",   "family": "diag",      "min": (460, 360),  "pref": (700, 640)},
    "_running_servers":  {"tier": "status",   "family": "framework", "min": (340, 220),  "pref": (460, 360)},
    "_log":              {"tier": "status",   "family": "framework", "min": (420, 160),  "pref": (900, 300)},
    "pdxc":              {"tier": "rare",     "family": "control",   "min": (320, 240),  "pref": (420, 320)},
    "tpi":               {"tier": "rare",     "family": "control",   "min": (400, 300),  "pref": (520, 400)},
    "remote_control":    {"tier": "rare",     "family": "control",   "min": (300, 200),  "pref": (400, 300)},
    "ethernet_relay":    {"tier": "rare",     "family": "control",   "min": (300, 200),  "pref": (380, 280)},
}
