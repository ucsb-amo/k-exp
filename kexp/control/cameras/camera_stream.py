"""Per-shot frames from an auxiliary camera, for a kexp experiment.

    self.cam = camera_stream(self, cameras.mot_basler, 'img_mot')             # free-run
    self.cam = camera_stream(self, cameras.z_basler, ['img_a', 'img_b'],
                             mode='triggered')                                # TTL-triggered

Call it in ``prepare()`` before ``finish_prepare()``. Free-run: ``grab(t)``
in the kernel snaps a frame about ``t`` after the cursor. Triggered: the
camera waits for edges on its trigger line (the entry's ``trigger_ttl`` /
``trigger_source`` in kexp.config.camera_id) and ``trigger(j)`` exposes
frame ``j`` at the cursor. See waxx.control.cameras.camera_stream_client.

Nothing here touches the network: the stream objects (what the kernel
sees: class, trigger line, exposure delay) are built from the config, and
their containers registered with a provisional shape. The cameras are
connected by the run's claim (kexp Base.claim_hardware ->
``connect_camera_streams``), in parallel -- for a warm-launched run after
the kernel was compiled; the probe frame then gives the containers their
shape.

A camera that is this run's acquisition camera, or (triggered) is wired to
the run camera's trigger line, gets a placeholder (DummyCameraStreamClient).
A camera that cannot be connected with ``on_error='dummy'`` becomes a dead
stream (no frames, its kernel calls counted, a placeholder record); the
default, ``'raise'``, stops the run in its claim instead, before it has a
run id. Triggered streams whose cameras share a trigger line are made
siblings. A camera on liveOD's bar is leased from liveOD.

``camera_streams(expt, specs)`` builds several streams at once
(DiagnosticImages uses it).
"""

import logging
from types import SimpleNamespace

from beacon.camera.directory import query_string
from waxx.control.cameras.camera_stream_client import (
    CameraStreamClient, DummyCameraStreamClient, TriggeredCameraStreamClient,
    connect_streams, link_trigger_line)
from waxx.util import console

from kexp.config.camera_id import cameras, camera_trigger_ttl, CameraParams

MODES = ('free_run', 'triggered')
ON_ERROR = ('raise', 'dummy')


def _drop_claimed_by(record):
    # A camera listed by both the beacon server and liveOD is routine in an
    # experiment (the run camera, a lent Basler); a stream on the wrong server
    # fails loudly on its own.
    return "is claimed by" not in record.getMessage()


def _quiet_directory_in_experiment():
    log = logging.getLogger("beacon.camera.directory")
    if _drop_claimed_by not in log.filters:
        log.addFilter(_drop_claimed_by)


def camera_stream(expt, camera, key, *, mode='free_run', exposure_time=None,
                  gain=None, t_snap_lead=0.12, on_error='raise',
                  trigger_source=None, **kw):
    """A stream on ``camera`` (a cameras.* entry, serial or name) saving
    frames under ``key`` (triggered mode: a list, one key per frame).
    ``exposure_time`` (s) / ``gain`` (dB) override the camera's saved
    defaults; ``trigger_source`` overrides the entry's input line (for
    finding out where a trigger is wired); other keywords go to the client
    (``frame_settings``, ``no_roi_downsample``, ...)."""
    spec = dict(camera=camera, key=key, mode=mode, exposure_time=exposure_time,
                gain=gain, t_snap_lead=t_snap_lead, on_error=on_error,
                trigger_source=trigger_source, **kw)
    return camera_streams(expt, [spec])[0]


def camera_streams(expt, specs):
    """Several streams at once: ``specs`` is a list of dicts of
    ``camera_stream``'s arguments (``camera``, ``key`` and its keywords).

    No network (see the module docstring): per spec, in ``specs`` order, the
    checks, then its stream object, its containers (provisional shape), its
    place in ``expt.camera_streams``, its trigger-line siblings -- or its
    placeholder / failure. A spec that fails to build with
    ``on_error='raise'`` raises after the streams before it are registered.
    The run's claim connects them (``connect_camera_streams``). Returns the
    streams in ``specs`` order."""
    _quiet_directory_in_experiment()
    taken = set()
    plans = [_plan(expt, dict(s), taken) for s in specs]

    out = []
    for i, p in enumerate(plans):
        if p.placeholder is not None:
            out.append(_placeholder(expt, p, p.placeholder))
            continue
        error = p.error
        if error is None:
            _build(p)
            error = p.error
        if error is None:
            siblings = ([s for s in expt.camera_streams if getattr(s, 'ttl', None) is p.ttl]
                        if p.triggered else [])
            try:
                p.stream.register()
            except Exception as e:
                p.stream.abandon()
                error = e
        if error is not None:
            if p.on_error == 'raise':
                raise error
            print(f"[camera_stream:{p.name}] !! {p.serial} could not be set up ({error!r}); "
                  f"no such frames this run")
            out.append(_placeholder(expt, p, f"setup failed: {error!r}"))
            continue
        cs = p.stream
        if siblings:
            link_trigger_line(cs, *siblings)
            console.info(f"[{cs.label}] shares ttl.{p.entry.trigger_ttl} with "
                         + ", ".join(s.label for s in siblings)
                         + ": each keeps only its own frames", console.VERBOSE)
        out.append(cs)
    return out


def connect_camera_streams(expt):
    """The run's claim: connect every camera stream of ``expt`` built
    without a connection, in parallel (waxx connect_streams: activate each
    that connected, mark dead / raise per its on_error). Before the liveOD
    start payload is built: the containers get their real shapes here."""
    return connect_streams(list(getattr(expt, 'camera_streams', ())))


def _plan(expt, spec, taken):
    """What one spec will be: a placeholder, a failure, or a constructor to
    run (``ctor``; it builds the stream without a connection). Raises for a bad mode / on_error or a camera already
    streaming this run, as camera_stream always has."""
    camera = spec.pop('camera')
    key = spec.pop('key')
    mode = spec.pop('mode', 'free_run')
    on_error = spec.pop('on_error', 'raise')
    exposure_time = spec.pop('exposure_time', None)
    gain = spec.pop('gain', None)
    t_snap_lead = spec.pop('t_snap_lead', 0.12)
    trigger_source = spec.pop('trigger_source', None)
    kw = spec
    if mode not in MODES:
        raise ValueError(f"camera_stream mode {mode!r} is not one of {MODES}")
    if on_error not in ON_ERROR:
        raise ValueError(f"camera_stream on_error {on_error!r} is not one of {ON_ERROR}")
    triggered = mode == 'triggered'
    name = key if isinstance(key, str) else key[0]
    serial = query_string(camera)
    run_cam = expt.camera_params if expt.setup_camera else None
    p = SimpleNamespace(key=key, name=name, serial=serial, triggered=triggered,
                        on_error=on_error, ttl=None, entry=None, ctor=None,
                        placeholder=None, error=None, stream=None)

    if run_cam is not None and str(getattr(run_cam, 'serial_no', '')) == serial:
        p.placeholder = f"{serial} is this run's acquisition camera ({run_cam.key})"
        return p
    for other in expt.camera_streams:
        if getattr(other, 'serial', None) == serial:
            raise ValueError(f"camera_stream '{name}': {serial} already has the stream "
                             f"'{other.key}' this run -- give that stream another key")
    if serial in taken:
        raise ValueError(f"camera_stream '{name}': {serial} is asked for twice "
                         f"in one camera_streams call")
    live_od_client = getattr(expt, 'live_od_client', None)

    try:
        if not triggered:
            p.ctor = lambda: CameraStreamClient(
                expt, serial, key, exposure_time=exposure_time, gain=gain,
                t_snap_lead=t_snap_lead, live_od_client=live_od_client,
                defer_register=True, connect=False, on_error=on_error, **kw)
        else:
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
                p.placeholder = (f"'{entry.key}' shares trigger line ttl.{entry.trigger_ttl} "
                                 f"with this run's acquisition camera '{run_cam.key}'")
                return p
            p.entry, p.ttl = entry, ttl
            p.ctor = lambda: TriggeredCameraStreamClient(
                expt, serial, key, ttl=ttl,
                trigger_source=trigger_source or entry.trigger_source,
                exposure_delay=entry.exposure_delay, t_trigger=entry.t_camera_trigger,
                exposure_time=exposure_time, gain=gain, live_od_client=live_od_client,
                defer_register=True, connect=False, on_error=on_error, **kw)
    except Exception as e:
        if on_error == 'raise':
            raise
        p.error = e
        return p
    taken.add(serial)
    return p


def _build(p):
    """Build the plan's stream object (no network: connect=False)."""
    try:
        p.stream = p.ctor()
    except Exception as e:
        p.error = e


def _placeholder(expt, p, reason):
    return DummyCameraStreamClient(expt, p.key, reason=reason, triggered=p.triggered)


def _entry_by_serial(serial):
    for params in vars(cameras).values():
        if isinstance(params, CameraParams) and str(getattr(params, 'serial_no', '')) == serial:
            return params
    return None
