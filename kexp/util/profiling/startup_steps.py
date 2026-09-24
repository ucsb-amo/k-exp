"""kexp's host-side steps for the waxx startup timer (the `art` launcher).

Loaded BY PATH by waxx/util/profiling/startup_timer.py (--host-steps-file), never
imported: importing anything under kexp here would run kexp/__init__ before the
timer starts and hide kexp's import cost. Keep this file free of imports.

Each entry is (module, class, method, label). HOST-ONLY methods only -- a method
that a kernel calls (an RPC target, e.g. tweezer.awg_init) must not be wrapped.
"""

HOST_STEPS = [
    ("kexp.base.base", "Base", "__init__", "Base.__init__"),
    ("kexp.base.devices", "Devices", "prepare_devices", "prepare_devices"),
    ("kexp.config.wavemeter_id", "fzw_frame", "__init__", "wavemeter frame (TCP connect)"),
    ("kexp.base.clients", "Clients", "__init__", "Clients.__init__ (server discovery)"),
    ("kexp.control.misc.pdxc_apd_stage", "APDStageClient", "set_apd_stage", "set_apd_stage"),
    ("kexp.base.base", "Base", "finish_prepare", "finish_prepare"),
    ("waxx.util.live_od.live_od_client", "LiveODClient", "init_run", "liveOD INIT_RUN"),
    ("waxx.util.live_od.live_od_client", "LiveODClient", "wait_cam_ready",
     "liveOD WAIT_CAM_READY"),
    ("waxx.util.live_od.live_od_client", "LiveODClient", "end_run", "liveOD END_RUN"),
]
