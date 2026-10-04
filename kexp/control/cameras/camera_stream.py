"""Per-shot frames from an auxiliary camera, for a kexp experiment.

    self.cam = camera_stream(self, cameras.mot_basler, 'img_mot')             # free-run
    self.cam = camera_stream(self, cameras.z_basler, ['img_a', 'img_b'],
                             mode='triggered')                                # TTL-triggered

Call it in ``prepare()`` before ``finish_prepare()``. Free-run: ``grab(t)``
in the kernel snaps a frame about ``t`` after the cursor. Triggered: the
camera waits for edges on its trigger line (the entry's ``trigger_ttl`` /
``trigger_source`` in kexp.config.camera_id) and ``trigger(j)`` exposes
frame ``j`` at the cursor. See waxx.control.cameras.camera_stream_client.

A camera that is this run's acquisition camera, or (triggered) is wired to
the run camera's trigger line, gets a placeholder (DummyCameraStreamClient);
so does one that cannot be set up when ``on_error='dummy'`` (the default,
``'raise'``, fails prepare() instead). Triggered streams whose cameras share
a trigger line are made siblings. A camera on liveOD's bar is leased from
liveOD.
"""

from beacon.camera.directory import query_string
from waxx.control.cameras.camera_stream_client import (
    CameraStreamClient, DummyCameraStreamClient, TriggeredCameraStreamClient,
    link_trigger_line)
from waxx.util import console

from kexp.config.camera_id import cameras, camera_trigger_ttl, CameraParams

MODES = ('free_run', 'triggered')
ON_ERROR = ('raise', 'dummy')


def camera_stream(expt, camera, key, *, mode='free_run', exposure_time=None,
                  gain=None, t_snap_lead=0.12, on_error='raise',
                  trigger_source=None, **kw):
    """A stream on ``camera`` (a cameras.* entry, serial or name) saving
    frames under ``key`` (triggered mode: a list, one key per frame).
    ``exposure_time`` (s) / ``gain`` (dB) override the camera's saved
    defaults; ``trigger_source`` overrides the entry's input line (for
    finding out where a trigger is wired); other keywords go to the client
    (``frame_settings``, ``no_roi_downsample``, ...)."""
    if mode not in MODES:
        raise ValueError(f"camera_stream mode {mode!r} is not one of {MODES}")
    if on_error not in ON_ERROR:
        raise ValueError(f"camera_stream on_error {on_error!r} is not one of {ON_ERROR}")
    triggered = mode == 'triggered'
    name = key if isinstance(key, str) else key[0]
    serial = query_string(camera)
    run_cam = expt.camera_params if expt.setup_camera else None

    def placeholder(reason):
        return DummyCameraStreamClient(expt, key, reason=reason, triggered=triggered)

    if run_cam is not None and str(getattr(run_cam, 'serial_no', '')) == serial:
        return placeholder(f"{serial} is this run's acquisition camera ({run_cam.key})")
    for other in expt.camera_streams:
        if getattr(other, 'serial', None) == serial:
            raise ValueError(f"camera_stream '{name}': {serial} already has the stream "
                             f"'{other.key}' this run -- give that stream another key")
    live_od_client = getattr(expt, 'live_od_client', None)

    try:
        if not triggered:
            return CameraStreamClient(expt, serial, key, exposure_time=exposure_time,
                                      gain=gain, t_snap_lead=t_snap_lead,
                                      live_od_client=live_od_client, **kw)

        entry = camera if isinstance(camera, CameraParams) else _entry_by_serial(serial)
        if entry is None:
            raise ValueError(f"camera_stream '{name}': no kexp.config.camera_id entry "
                             f"has serial {serial}")
        if entry.camera_type != 'basler':
            raise ValueError(f"camera_stream '{name}': triggered mode is for Basler "
                             f"cameras, and '{entry.key}' is a {entry.camera_type}")
        ttl = camera_trigger_ttl(expt.ttl, entry)
        if run_cam is not None and getattr(run_cam, 'trigger_ttl', '') == entry.trigger_ttl:
            # one pulse on the line would expose the run camera too
            return placeholder(f"'{entry.key}' shares trigger line ttl.{entry.trigger_ttl} "
                               f"with this run's acquisition camera '{run_cam.key}'")
        siblings = [s for s in expt.camera_streams if getattr(s, 'ttl', None) is ttl]
        cs = TriggeredCameraStreamClient(
            expt, serial, key, ttl=ttl,
            trigger_source=trigger_source or entry.trigger_source,
            exposure_delay=entry.exposure_delay, t_trigger=entry.t_camera_trigger,
            exposure_time=exposure_time, gain=gain, live_od_client=live_od_client, **kw)
        if siblings:
            link_trigger_line(cs, *siblings)
            console.info(f"[{cs.label}] shares ttl.{entry.trigger_ttl} with "
                         + ", ".join(s.label for s in siblings)
                         + ": each keeps only its own frames", console.VERBOSE)
        return cs
    except Exception as e:
        if on_error == 'raise':
            raise
        print(f"[camera_stream:{name}] !! {serial} could not be set up ({e!r}); "
              f"no such frames this run")
        return placeholder(f"setup failed: {e!r}")


def _entry_by_serial(serial):
    for params in vars(cameras).values():
        if isinstance(params, CameraParams) and str(getattr(params, 'serial_no', '')) == serial:
            return params
    return None
