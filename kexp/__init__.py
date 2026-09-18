from .base.base import Base
from .base.adjust import Adjust
from .config.dds_id import dds_frame
from waxa import img_types
from kexp.config.camera_id import cameras, CameraParams
from kexp.control.ethernet_relay import EthernetRelay
from kexp.util.artiq.async_print import aprint

# The analysis names are lazy (PEP 562).  Importing them here eagerly made every
# experiment process load the whole analysis stack (scipy, matplotlib, pandas,
# cv2, joblib, ARC + sympy -- about 1 s per run) that only notebooks use.
# `from kexp import atomdata` and `kexp.atomdata` work exactly as before; the
# import happens on first access.  The TYPE_CHECKING block keeps editor
# highlighting / go-to-definition unchanged.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from waxa import atomdata, load_atomdata, AtomdataVault

_lazy_waxa = ('atomdata', 'load_atomdata', 'AtomdataVault')

def __getattr__(name):
    if name in _lazy_waxa:
        import waxa
        val = getattr(waxa, name)
        globals()[name] = val
        return val
    raise AttributeError(f"module 'kexp' has no attribute {name!r}")

def __dir__():
    return sorted(list(globals()) + list(_lazy_waxa))
