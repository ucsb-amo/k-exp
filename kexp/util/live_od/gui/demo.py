"""Alias of waxx.util.live_od.gui.demo (liveOD is lab-independent and lives in waxx).

Never lived in kexp; here so that every waxx liveOD module has a kexp path.
Importing it gives you the waxx module itself; running it
(`python -m kexp.util.live_od.gui.demo`) runs the waxx module.
"""
import sys as _sys

import waxx.util.live_od.gui.demo as _impl

# names on this module object too, for code that loads this file by path
globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})

if __name__ == "__main__":
    import runpy as _runpy
    _runpy.run_module("waxx.util.live_od.gui.demo", run_name="__main__")
else:
    _sys.modules[__name__] = _impl
