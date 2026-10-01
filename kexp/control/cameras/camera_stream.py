"""K-machine factory for per-shot auxiliary camera grabs.

``camera_stream(self, cameras.mot_basler, 'img_mot')`` in ``prepare()``
(before ``finish_prepare``) gives a ``CameraStreamClient`` snapping that
camera once per shot when ``grab(t_offset)`` is called in ``scan_kernel``
-- see ``waxx.control.cameras.camera_stream_client`` for the model.

If the requested camera is this run's own acquisition camera (liveOD
run-locks it from INIT_RUN to the run's end, and an extra frame would corrupt
its frame accounting), a ``DummyCameraStreamClient`` is returned instead: the
kernel code compiles and runs unchanged, the key gets placeholder containers
(one byte per shot, ``<key>_seq`` -1 everywhere) instead of frames, and a
one-line note plus the run's provenance say so.

Any other camera on liveOD's bar is leased from liveOD: liveOD borrows it
from the beacon server, opens it and serves the snaps, and the stream stays
on liveOD's server for the whole run.
"""

from beacon.camera.directory import query_string
from waxx.control.cameras.camera_stream_client import (CameraStreamClient,
                                                       DummyCameraStreamClient)


def camera_stream(expt, camera, key, *, exposure_time=None, gain=None,
                  t_snap_lead=0.12, **kw):
    """An auxiliary per-shot camera grabber for ``expt`` (kexp Base).

    Args:
        expt: the experiment (inside ``prepare()``, before finish_prepare).
        camera: a ``cameras.*`` params object, serial string or camera name.
        key: DataVault key for the frames; ``<key>_seq`` / ``<key>_t`` /
            ``<key>_t_target`` are registered alongside.
        exposure_time (s) / gain (dB): overrides for this run. Unset values
            come from the camera's saved beacon-server defaults.
        t_snap_lead (s): how early the snap is fired so the EXPOSURE lands
            near the grab target (snap request -> published frame measured at
            ~0.15-0.25 s on kong, 2026-09-30). ``<key>_t`` records the true
            publish time per shot either way.
    """
    serial = query_string(camera)
    run_cam = getattr(expt, "camera_params", None)
    if (expt.setup_camera and run_cam is not None
            and str(getattr(run_cam, "serial_no", "")) == serial):
        return DummyCameraStreamClient(
            expt, key,
            reason=f"{serial} is this run's acquisition camera "
                   f"({getattr(run_cam, 'key', '?')})")
    return CameraStreamClient(
        expt, serial, key,
        exposure_time=exposure_time, gain=gain, t_snap_lead=t_snap_lead,
        live_od_client=getattr(expt, "live_od_client", None), **kw)
