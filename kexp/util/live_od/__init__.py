from os.path import dirname, basename, isfile, join
import glob
modules = glob.glob(join(dirname(__file__), "*.py"))
__all__ = [ basename(f)[:-3] for f in modules if isfile(f) and not f.endswith('__init__.py')]

# Lazy (PEP 562).  This __init__ runs in every experiment process, because
# Base's LiveODClient lives at kexp.util.live_od.live_od_client.  camera_mother
# imports waxa.atomdata and with it the whole analysis stack, which only the
# liveOD server process needs.  `from kexp.util.live_od import CameraMother`
# still works; the import happens on first access.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .camera_mother import CameraMother, CameraBaby, CameraNanny, DataHandler

_lazy_camera_mother = ('CameraMother', 'CameraBaby', 'CameraNanny', 'DataHandler')

def __getattr__(name):
    if name in _lazy_camera_mother:
        from . import camera_mother
        val = getattr(camera_mother, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'kexp.util.live_od' has no attribute {name!r}")
