"""Launcher for the liveOD remote viewer.

    python -m kexp.util.live_od.gui.remote_viewer_window [ip] [port]
                                                   (or _bat/live_od_viewer.bat)

The viewer is waxx.util.live_od.gui.remote_viewer_window. It needs no lab
configuration -- it builds itself from what liveOD broadcasts -- so this only
forwards to it; `python -m waxx.util.live_od.gui.remote_viewer_window` is the
same thing. `RemoteViewerWindow` and the rest of that module's names are
importable from here, as they always were.
"""
import runpy as _runpy

import waxx.util.live_od.gui.remote_viewer_window as _impl

globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})

if __name__ == '__main__':
    _runpy.run_module("waxx.util.live_od.gui.remote_viewer_window", run_name="__main__")
