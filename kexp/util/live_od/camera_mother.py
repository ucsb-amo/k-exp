"""Moved to waxx.util.live_od.camera_mother on 2026-09-18 (liveOD is lab-independent
and lives in waxx). Kept so every existing import keeps working: the classes here
are the waxx objects themselves, not copies.

Unlike the other modules in this folder this one is not a pure alias, because it
keeps two module-level names the waxx module dropped. Nothing ever used them; the
old definition raised TypeError on a PC with no data-directory environment
variable set, and this one does not.
"""
import os as _os

import waxx.util.live_od.camera_mother as _impl

globals().update({_k: _v for _k, _v in vars(_impl).items() if not _k.startswith("__")})

DATA_DIR = _os.getenv("data")
RUN_ID_PATH = _os.path.join(DATA_DIR, "run_id.py") if DATA_DIR else None
