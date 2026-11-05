"""Alias of waxx.util.live_od.data.image_writer (liveOD is lab-independent and lives in waxx).

Never lived in kexp; here so that every waxx liveOD module has a kexp path.
Importing it gives you the waxx module itself.
"""
import sys as _sys

import waxx.util.live_od.data.image_writer as _impl

# names on this module object too, for code that loads this file by path
globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})
_sys.modules[__name__] = _impl
