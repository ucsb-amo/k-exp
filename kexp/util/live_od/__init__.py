"""liveOD moved to waxx.util.live_od on 2026-09-18: it is lab-independent, and waxx
and waxa already owned its protocol. What stays in kexp:

  * kexp/config/live_od.py -- everything the K machine tells liveOD;
  * gui/main_window.py, gui/remote_viewer_window.py -- the launchers behind
    _bat/live_od.bat and _bat/live_od_viewer.bat (and `python -m ...`);
  * every other module here, as an alias of the waxx module of the same name, so
    existing imports keep working.

Lazy (PEP 562), and free of module-level imports: Base's LiveODClient is imported
as kexp.util.live_od.live_od_client, so this file runs in every experiment
process, which must not pay for cameras, Qt or the analysis stack.
"""
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from waxx.util.live_od.camera_mother import CameraMother, CameraBaby, CameraNanny, DataHandler

_lazy_acquisition = ('CameraMother', 'CameraBaby', 'CameraNanny', 'DataHandler')

__all__ = ['camera_connection_widget', 'camera_mother', 'camera_nanny',
           'live_od_broadcaster', 'live_od_client', 'live_od_server', 'shot_cross_section']


def __getattr__(name):
    if name in _lazy_acquisition:
        import waxx.util.live_od as _waxx_live_od
        val = getattr(_waxx_live_od, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'kexp.util.live_od' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_lazy_acquisition))
