from artiq.experiment import kernel, delay

from waxx.control.cameras.camera_param_classes import CameraParams, BaslerParams, AndorParams, APDParams, img_types
from waxx.config.camera_id import camera_frame as camera_frame_waxx

from kexp.config.ttl_id import ttl_frame

# The TTL lines the cameras' trigger inputs are wired to. This frame only
# names them (trigger_ttl=_ttl.<line> below): the experiment resolves each
# onto its own, device-bound ttl frame with camera_trigger_ttl.
_ttl = ttl_frame()


class camera_frame(camera_frame_waxx):
    def __init__(self):

        self.setup()

        # Andor DU897_EXF vertical-clock settings. Dark-frame CIC sweep on
        # 2026-09-23 (EM gain 300, 10 us exposure, -63 C, 20 frames/config,
        # fixed threshold = gain-1 bias + 6 sigma):
        #   vs=0.5 us, +3 (old):    2.7e-2 events/pix/frame, readout 18.1 ms
        #   vs=0.3 us, Normal:       3.9e-4 events/pix/frame, readout 17.9 ms
        # 2026-09-24, runs 80707 (0.5 us/+3) vs 80708 (0.3 us/Normal), same
        # beam-only sequence: at 0.3 us / Normal the light frames contain NO
        # image (light - dark peak 38 ADU vs 9400 ADU), dark sigma drops to
        # read noise. The charge is not transferred at that clock, so the low
        # dark-frame count in the sweep was signal loss, not low CIC. Do not
        # use it. Beam check: tools/readout_clock_smear_test.py.
        # Frame gaps: readout 18.1 ms + keep-clean 3.9 ms + margin; 30 ms
        # validated at 0.5 us/+3 in run 80707 (no lost frames).
        self.andor = AndorParams(amp_absorption=.2, exposure_time_abs=10.e-6, em_gain_abs=300.,
                                amp_fluorescence=0.5, exposure_time_fluor=25.e-6, em_gain_fluor=1.,
                                amp_dispersive=0.2, exposure_time_dispersive=5.e-6, em_gain_dispersive=300.,
                                magnification=16.4, # based on run 49189, updated 2025-11-20
                                # t_light_only_image_delay=50.e-3, # 2026-09-23
                                # t_dark_image_delay=50.e-3, # 2026-09-23
                                t_light_only_image_delay=30.e-3, # 2026-09-23
                                t_dark_image_delay=30.e-3, # 2026-09-23
                                hs_speed=0, preamp=2,
                                vs_speed=1, vs_amp=3, # restored 2026-09-24, run 80707/80708
                                baseline_clamp=1,
                                # 2026-09-26: run-owned fields; only these values are accepted for runs
                                trigger_mode="ext", frame_transfer=0, sensor_roi=(0, 512, 0, 512, 1, 1),
                                trigger_ttl=_ttl.andor)

        # The APD sits behind the Andor's pickoff beamsplitter, and keeps
        # clocking the Andor trigger line so its imaging sequence is
        # bit-identical to an Andor run.
        self.apd = APDParams(amp_absorption=.2, exposure_time_abs=20.e-6,
                            amp_fluorescence=0.5, exposure_time_fluor=25.e-6,
                            amp_dispersive=0.2, exposure_time_dispersive=5.e-6,
                            t_light_only_image_delay=50.e-3,
                            t_dark_image_delay=50.e-3,
                            trigger_ttl=_ttl.andor)

        self.xy_basler = BaslerParams(serial_number='40316451',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.5, gain_abs=6.,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    magnification=0.5,
                                    trigger_ttl=_ttl.basler)

        # Its own camera and settings, but triggered from the same TTL line as
        # the MOT basler (rewired by the user 2026-10-01; was ttl.z_basler): a
        # pulse on ttl.mot_basler_trigger reaches both. The diagnostic streams
        # (kexp.control.cameras.diagnostic_images) are siblings on that line.
        self.x_basler = BaslerParams(serial_number='40320384',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.248,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    trigger_source='Line2',
                                    trigger_ttl=_ttl.mot_basler_trigger)

        self.z_basler = BaslerParams(serial_number='40416468',
                                    exposure_time_fluor = 1.e-3, amp_fluorescence=0.5,
                                    exposure_time_abs = 19.e-6, amp_absorption = 0.5,gain_abs=24.,
                                    exposure_time_dispersive = 100.e-6, amp_dispersive = 0.248,
                                    trigger_ttl=_ttl.z_basler)

        self.basler_2dmot = BaslerParams(serial_number='40277703',
                                         trigger_source='Line2',
                                         trigger_ttl=_ttl.basler_2dmot)

        # MOT fluorescence monitor, served by the beacon Basler server on kong
        # -- not on liveOD's bar. Used by the MOT viewer and by per-shot aux
        # grabs (kexp.control.cameras.camera_stream). Trigger wired to
        # ttl.mot_basler_trigger on Line2 (user, 2026-10-01). Sensor model
        # unverified: resolution/magnification are NOT trustworthy for this
        # entry (frame size is auto-detected at grab setup); pixel size
        # 3.45 um per user, 2026-09-30.
        self.mot_basler = BaslerParams(serial_number='40277706',
                                       trigger_source='Line2',
                                       trigger_ttl=_ttl.mot_basler_trigger)

        self.cleanup()

cameras = camera_frame()


def camera_trigger_ttl(ttl, camera):
    """The TTL object on the experiment's ttl frame `ttl` wired to `camera`'s
    trigger input: the frame's attribute named by the entry's `trigger_ttl`,
    or, failing that, its TTL on channel `trigger_ttl_ch`. The entry's own
    `_trigger_ttl` object is never returned -- it belongs to this module's
    unbound frame, not to the experiment's devices. Raises ValueError for an
    entry with no trigger, or one the frame does not have."""
    name = getattr(camera, 'trigger_ttl', '')
    ch = int(getattr(camera, 'trigger_ttl_ch', -1))
    if not name and ch < 0:
        raise ValueError(
            f"No camera TTL mapping found for camera key '{camera.key}' "
            f"(set trigger_ttl on its entry in kexp.config.camera_id).")
    if name and hasattr(ttl, name):
        return getattr(ttl, name)
    if ch >= 0:
        for t in getattr(ttl, 'ttl_list', ()):
            if getattr(t, 'ch', None) == ch:
                return t
    raise ValueError(
        f"Camera '{camera.key}' names trigger_ttl '{name}' (ch {ch}), which "
        f"is not a TTL in kexp.config.ttl_id.")


_SHOW = ('image', 'counts', None)


class DiagnosticImage:
    """One frame a diagnostic camera takes every shot.

    ``key``    DataVault key the frame is saved under (+ ``<key>_meta``).
    ``at``     the hook that fires it: a hook method of kexp.control.cameras
               .diagnostic_images.DiagnosticImages (``mot_beams_on``,
               ``tweezer_evap``, ...), called by the sequence at that moment.
    ``t``      offset from the hook, s (negative: before it).
    ``exposure_time`` (s), ``gain`` (dB): this frame's own settings (None:
               the camera's).
    ``label``, ``show``: for the diagnostic viewer -- 'image' (shown as an
               image), 'counts' (a table row) or None (not shown).

    Bound to its camera for a run (DiagnosticImages), it knows its frame
    index ``j`` and fires with ``trigger()``. Tag value changes with a run
    id, like a calibration."""

    def __init__(self, key, at, t=0., exposure_time=None, gain=None,
                 label=None, show='counts'):
        if not str(key).isidentifier():
            raise ValueError(f"DiagnosticImage key {key!r} is not an identifier")
        if show not in _SHOW:
            raise ValueError(f"DiagnosticImage {key!r}: show={show!r}, not one of {_SHOW}")
        self.key = str(key)
        self.at = str(at)
        self.t = float(t)
        self.exposure_time = None if exposure_time is None else float(exposure_time)
        self.gain = None if gain is None else float(gain)
        self.label = label or self.key.removeprefix('img_').replace('_', ' ')
        self.show = show
        # set when DiagnosticImages binds a run's copy
        self.j = -1
        self.camera = None

    def settings(self):
        """This frame's own exposure / gain ({} when it has none)."""
        return {k: v for k, v in (('exposure_time', self.exposure_time),
                                  ('gain', self.gain)) if v is not None}

    def __repr__(self):
        args = [repr(self.key), f"at={self.at!r}", f"t={self.t!r}"]
        args += [f"{k}={v!r}" for k, v in self.settings().items()]
        if self.label != DiagnosticImage(self.key, self.at).label:
            args.append(f"label={self.label!r}")
        if self.show != 'counts':
            args.append(f"show={self.show!r}")
        return f"DiagnosticImage({', '.join(args)})"

    @kernel
    def trigger(self, t_stage=0.):
        """This frame, ``t`` from the cursor; the cursor stays. With
        ``t_stage`` > 0 -- the length of the stage the hook starts (frames
        after it) or ends (frames before it) -- a frame outside it is
        skipped."""
        if t_stage <= 0. or (self.t <= t_stage and -self.t <= t_stage):
            self.camera.trigger(self.j, self.t)


class DiagnosticCamera:
    """One camera of the per-shot diagnostics: its ``cameras`` entry (which
    must name its ``trigger_ttl``), the DiagnosticImages it takes per shot --
    listed in the order the sequence reaches them; frame index = position --
    and the exposure_time (s), gain (dB) and viewer ROI ``[x1, y1, x2, y2]``
    it runs at (None = the camera's saved beacon-server defaults). ``label``
    names it in the diagnostic viewer. The camera viewer's Save button copies
    a line in this form (right-click)."""

    def __init__(self, camera, images=(), exposure_time=None, gain=None, roi=None,
                 label=None):
        self.camera = camera
        self.images = list(images)
        self.exposure_time = exposure_time
        self.gain = gain
        self.roi = [int(v) for v in roi] if roi else None
        self.label = label or str(getattr(camera, 'key', '')).replace('_', ' ')
        keys = self.frames
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise ValueError(f"DiagnosticCamera {self.label!r}: frames {dup} listed twice")
        self.key = ""       # attribute name, written by diagnostic_frame
        # set when DiagnosticImages binds a run's copy
        self.stream = None
        self.diag = None

    @property
    def frames(self):
        """The frame keys, in frame-index order."""
        return [img.key for img in self.images]

    @property
    def frame_settings(self):
        """{frame key: its own exposure / gain} for the frames that have them."""
        return {img.key: img.settings() for img in self.images if img.settings()}

    def frame_index(self, key):
        """The index of frame ``key`` on this camera, -1 if it takes none."""
        return self.frames.index(key) if key in self.frames else -1

    @kernel
    def trigger(self, j, t):
        """Frame ``j``, ``t`` (s) after the cursor; the cursor stays. Nothing
        while diagnostics are inactive (off, or a warm-up shot)."""
        if self.diag.active:
            delay(t)
            self.stream.trigger(j)
            delay(-t)


class diagnostic_frame:
    """The cameras every data-saving run takes reference frames with
    (Base(diagnostic_images=True); fired by kexp.control.cameras
    .diagnostic_images). Each DiagnosticImage says where in the sequence it
    is taken (``at`` a hook, ``t`` from it). Entries are built in order;
    cameras on one trigger line (mot, x) become siblings.

    New frame: a DiagnosticImage in its camera's list. New camera: an entry
    here (and ``trigger_ttl`` on its ``cameras`` entry). New moment in the
    sequence: a hook in DiagnosticImages and its call in the sequence."""

    def __init__(self):
        # values settled 2026-10-01 (runs 84546-84574). Offsets were ExptParams
        # t_diag_* until 2026-10-19; their history moved here with them.
        # The 2D-MOT and MOT baslers (Basler a2A3840-45um, rolling shutter)
        # expose a mid-sensor ROI ~15-40 ms AFTER the trigger edge: lead the
        # moment of interest by that much, and keep the scene static for the
        # ROI's row span (~16 ms). Edges on one trigger line >~50 ms apart.

        # img_2dmot: t = -10 ms saw the push on (84547-84556), 2026-10-01 -> -60 ms #84556, 2026-10-01
        self.mot_2d = DiagnosticCamera(cameras.basler_2dmot, label='2D-MOT basler',
                                       exposure_time=3.5e-3, gain=20., roi=[1685, 741, 1959, 1022],
                                       images=[DiagnosticImage('img_2dmot', at='mot_push_on', t=-60.e-3,
                                                               label='2D MOT fluorescence', show='image')])

        # 19 us / 0 dB is the minimum; the MOT-beam frame still saturates at its bright edge,
        # the GM-beam frame peaked at 29 DN there (84858-84867) -> its own gain
        self.xy = DiagnosticCamera(cameras.xy_basler, label='xy basler',
                                   exposure_time=19.e-6, gain=0., roi=[382, 398, 943, 755],
                                   images=[DiagnosticImage('img_mot_beams_xy', at='mot_beams_on', t=5.e-3,
                                                           label='MOT beams'),
                                           DiagnosticImage('img_gm_beams_xy', at='gm_beams_on', t=0.25e-3,
                                                           gain=18., label='GM beams')])

        # lightsheet frames dropped: this camera does not see the lightsheet (blank up to 20 ms / 20 dB;
        # they were at lightsheet_load t = 50 ms and lightsheet_evap t = 3 ms, 2 ms / 20 dB)
        self.z = DiagnosticCamera(cameras.z_basler, label='z basler',
                                  exposure_time=19.e-6, gain=0., roi=[660, 300, 1260, 900],
                                  images=[DiagnosticImage('img_mot_beams_z', at='mot_beams_on', t=5.e-3,
                                                          label='MOT beams'),
                                          DiagnosticImage('img_gm_beams_z', at='gm_beams_on', t=0.25e-3,
                                                          label='GM beams')])

        # img_mot: t = -50 ms (2026-10-01) -> -150 ms #84561, 2026-10-01 (>= 100 ms from the GM edge)
        # img_gm: 0.5 ms before GM end was blank, the ROI exposed after GM (84546-84561) -> triggered
        #   25 ms before GM starts #84561, 2026-10-01: a rolling exposure across CMOT end, GM and the
        #   ramp start; blank at the MOT settings (max 1 DN, 84858-84867): the whole GM at full gain
        self.mot = DiagnosticCamera(cameras.mot_basler, label='MOT basler',
                                    exposure_time=300.e-6, gain=3., roi=[1668, 1049, 2373, 1767],
                                    images=[DiagnosticImage('img_mot', at='mot_load_end', t=-150.e-3,
                                                            label='MOT fluorescence', show='image'),
                                            DiagnosticImage('img_gm', at='cmot_end', t=-25.e-3,
                                                            exposure_time=3.e-3, gain=30.,
                                                            label='GM fluorescence', show='image')])

        # shares the MOT basler's trigger line
        self.x = DiagnosticCamera(cameras.x_basler, label='x basler',
                                  exposure_time=300.e-6, gain=30., roi=[1511, 141, 1729, 788],
                                  images=[DiagnosticImage('img_tweezer_load_x', at='tweezer_load', t=1.e-3,
                                                          exposure_time=50.e-6, gain=5.,
                                                          label='tweezer load', show=None),
                                          DiagnosticImage('img_tweezer_evap_x', at='tweezer_evap', t=1.e-3,
                                                          label='tweezer evap', show=None)])

        # a camera with no saved viewer ROI stores its frames block-averaged this much
        self.no_roi_downsample = 4

        for name, entry in vars(self).items():
            if isinstance(entry, DiagnosticCamera):
                entry.key = name

    def entries(self):
        return [v for v in vars(self).values() if isinstance(v, DiagnosticCamera)]


diagnostic_cameras = diagnostic_frame()

