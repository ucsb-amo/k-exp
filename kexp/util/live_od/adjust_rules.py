"""Old path for waxx.util.live_od.adjust_rules (new in waxx 2026-11-04; liveOD is lab-independent and lives in waxx).

Kept so every liveOD module has its kexp path. It is not a copy and not a
subclass: importing it gives you the waxx module itself, so patching one
patches the other.
"""
import sys as _sys

import waxx.util.live_od.adjust_rules as _impl

# names on this module object too, for code that loads this file by path
globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})
_sys.modules[__name__] = _impl
