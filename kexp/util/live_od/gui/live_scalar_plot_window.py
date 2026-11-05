"""Moved to waxx.util.live_od.gui.live_scalar_plot_window on 2026-09-18 (liveOD is lab-independent and lives in waxx).

This module is kept so every existing import keeps working. It is not a copy and
not a subclass: importing it gives you the waxx module itself, so classes are the
same objects, private names are there, and patching one patches the other.
"""
import sys as _sys

import waxx.util.live_od.gui.live_scalar_plot_window as _impl

# names on this module object too, for code that loads this file by path
globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})
_sys.modules[__name__] = _impl
