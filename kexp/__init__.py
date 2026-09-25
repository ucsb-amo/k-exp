"""kexp -- K-machine ARTIQ experiment package.

Every public name here is lazy (PEP 562).  ``from kexp import Base`` and
``kexp.Base`` work exactly as before; the import happens on first access.

Why: ``Base`` drags in the AWG driver (spcm), the ARTIQ compiler and the
tweezer stack -- about 1.1 s -- and that used to be paid by every process
that merely imported ``kexp.config.*``: the dashboards, the Device Control
GUI, the remote-control panel, the monitor server.  None of them need
``Base``.  Experiments still pay it, on first access, exactly once.

The analysis names (``atomdata`` etc.) were already lazy for the same reason
(they load scipy / matplotlib / pandas / cv2 / ARC).

One difference from an eager module: ``from kexp import *`` does not pick up
lazy names (star-import ignores ``__getattr__``).  Nothing in the repos does
that.  The TYPE_CHECKING block keeps editor highlighting / go-to-definition
unchanged.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base.base import Base
    from .base.adjust import Adjust
    from .config.dds_id import dds_frame
    from waxa import img_types, atomdata, load_atomdata, AtomdataVault
    from kexp.config.camera_id import cameras, CameraParams
    from kexp.control.ethernet_relay import EthernetRelay
    from kexp.util.artiq.async_print import aprint

# name -> (module, attribute) for every lazily exported public name.
_LAZY = {
    'Base':          ('kexp.base.base', 'Base'),
    'Adjust':        ('kexp.base.adjust', 'Adjust'),
    'dds_frame':     ('kexp.config.dds_id', 'dds_frame'),
    'cameras':       ('kexp.config.camera_id', 'cameras'),
    'CameraParams':  ('kexp.config.camera_id', 'CameraParams'),
    'EthernetRelay': ('kexp.control.ethernet_relay', 'EthernetRelay'),
    'aprint':        ('kexp.util.artiq.async_print', 'aprint'),
    'img_types':     ('waxa', 'img_types'),
    'atomdata':      ('waxa', 'atomdata'),
    'load_atomdata': ('waxa', 'load_atomdata'),
    'AtomdataVault': ('waxa', 'AtomdataVault'),
}


def __getattr__(name):
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module 'kexp' has no attribute {name!r}")
    import importlib
    module_name, attr = target
    val = getattr(importlib.import_module(module_name), attr)
    globals()[name] = val
    return val


def __dir__():
    return sorted(set(globals()) | set(_LAZY))
