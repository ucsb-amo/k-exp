"""Reference images of the cooling sequence, taken every shot.

``Base.__init__(diagnostic_images=True)`` (the default for a run that saves
data) builds ``self.diag``, a DiagnosticImages: one triggered camera stream
per entry of ``kexp.config.camera_id.diagnostic_cameras`` (which cameras,
which frames, at what settings). The cooling sequence calls the kernel
methods below at its stage boundaries; an experiment with its own sequence
calls them itself. Each method takes its frame at the ``ExptParams``
``t_diag_*`` offset from the cursor it is called at, leaves the cursor where
it was, and does nothing with diagnostics off or during the warm-up shots
(``Base.pre_scan`` clears ``active`` around them: no frame is triggered,
fetched or stored for a shot that saves nothing).

    mot_2d()              in mot()'s push-off window     img_2dmot
    mot_beams()           3D beams switch-on             img_mot_beams_xy/_z
    mot_fluorescence(t)   3D beams switch-on             img_mot
    gm_fluorescence()     end of the D1 CMOT             img_gm
    gm_beams()            GM start                       img_gm_beams_xy/_z
    lightsheet_load()     end of the lightsheet ramp-up  img_lightsheet_load_z (*)
    lightsheet_evap()     end of lightsheet evap 1       img_lightsheet_evap_z (*)
    tweezer_load()        end of the tweezer ramp-up     img_tweezer_load_x
    tweezer_evap()        end of the last tweezer evap   img_tweezer_evap_x

(*) not configured: the z basler does not see the lightsheet (blank up to
20 ms / 20 dB, 2026-10-01); the hooks stay for a camera that does.

Each frame is saved under its key with a ``<key>_meta`` record per shot
(waxa.data.camera_frames) and a ``camera_stream_<key>`` provenance record.
The 2D-MOT and MOT baslers are rolling-shutter cameras whose ROI exposes
~15-40 ms after the edge: their offsets lead the moment of interest, and
the GM frame is a rolling exposure across CMOT end, GM and the ramp start.
"""

from artiq.experiment import kernel, delay

from waxx.control.cameras.camera_stream_client import (
    InactiveCameraStream, TriggeredCameraStreamClient)

from kexp.config.camera_id import diagnostic_cameras
from kexp.control.cameras.camera_stream import camera_stream

# camera entry key -> frame keys
DIAGNOSTIC_FRAMES = {e.camera.key: list(e.frames) for e in diagnostic_cameras.entries()}


class DiagnosticImages:

    def __init__(self, expt, enabled=True):
        self.enabled = bool(enabled)
        self.active = self.enabled      # kernel switch: Base.pre_scan clears it for the warm-up shots
        self.p = expt.params
        d = diagnostic_cameras
        self.streams = {}
        for entry in d.entries():
            if self.enabled:
                cs = camera_stream(expt, entry.camera, list(entry.frames),
                                   mode='triggered', on_error='dummy',
                                   exposure_time=entry.exposure_time, gain=entry.gain,
                                   roi=entry.roi,
                                   frame_settings=entry.frame_settings or None,
                                   no_roi_downsample=d.no_roi_downsample)
            else:
                cs = InactiveCameraStream(expt, list(entry.frames), reason="diagnostics off")
            self.streams[entry.key] = cs
        if self.enabled:
            up = [k for k, cs in self.streams.items()
                  if isinstance(cs, TriggeredCameraStreamClient)]
            down = [k for k in self.streams if k not in up]
            print("[diag cams] connected: " + (", ".join(up) or "none")
                  + (f" | NOT connected: {', '.join(down)}" if down else ""))
        self.cam_2dmot = self.streams['mot_2d']
        self.cam_xy = self.streams['xy']
        self.cam_z = self.streams['z']
        self.cam_mot = self.streams['mot']
        self.cam_x = self.streams['x']
        # frame index of each frame on its camera (-1: not configured)
        self.j_2dmot = d.mot_2d.frame_index('img_2dmot')
        self.j_mot_beams_xy = d.xy.frame_index('img_mot_beams_xy')
        self.j_gm_beams_xy = d.xy.frame_index('img_gm_beams_xy')
        self.j_mot_beams_z = d.z.frame_index('img_mot_beams_z')
        self.j_gm_beams_z = d.z.frame_index('img_gm_beams_z')
        self.j_lightsheet_load_z = d.z.frame_index('img_lightsheet_load_z')
        self.j_lightsheet_evap_z = d.z.frame_index('img_lightsheet_evap_z')
        self.j_mot = d.mot.frame_index('img_mot')
        self.j_gm = d.mot.frame_index('img_gm')
        self.j_tweezer_load_x = d.x.frame_index('img_tweezer_load_x')
        self.j_tweezer_evap_x = d.x.frame_index('img_tweezer_evap_x')

    @kernel
    def mot_2d(self):
        """2D MOT fluorescence at the cursor (mot() calls this
        t_diag_2dmot_before_push before the push comes on)."""
        if self.active and self.j_2dmot >= 0:
            self.cam_2dmot.trigger(self.j_2dmot)

    @kernel
    def mot_beams(self):
        """MOT beams on xy and z, t_diag_mot_beams_after_on after the cursor."""
        if self.active:
            delay(self.p.t_diag_mot_beams_after_on)
            if self.j_mot_beams_xy >= 0:
                self.cam_xy.trigger(self.j_mot_beams_xy)
            if self.j_mot_beams_z >= 0:
                self.cam_z.trigger(self.j_mot_beams_z)
            delay(-self.p.t_diag_mot_beams_after_on)

    @kernel
    def mot_fluorescence(self, t_load):
        """MOT fluorescence t_diag_mot_before_end before a load of t_load
        that starts at the cursor (skipped for a load too short for it)."""
        if (self.active and self.j_mot >= 0
                and t_load > self.p.t_diag_mot_before_end + self.p.t_diag_mot_beams_after_on):
            delay(t_load - self.p.t_diag_mot_before_end)
            self.cam_mot.trigger(self.j_mot)
            delay(-(t_load - self.p.t_diag_mot_before_end))

    @kernel
    def gm_fluorescence(self):
        """GM fluorescence, triggered t_diag_gm_trigger_lead before the
        cursor (GM start): the rolling shutter exposes that much later."""
        if self.active and self.j_gm >= 0:
            delay(-self.p.t_diag_gm_trigger_lead)
            self.cam_mot.trigger(self.j_gm)
            delay(self.p.t_diag_gm_trigger_lead)

    @kernel
    def gm_beams(self):
        """GM beams on xy and z, t_diag_gm_beams_after_start after the cursor."""
        if self.active:
            delay(self.p.t_diag_gm_beams_after_start)
            if self.j_gm_beams_xy >= 0:
                self.cam_xy.trigger(self.j_gm_beams_xy)
            if self.j_gm_beams_z >= 0:
                self.cam_z.trigger(self.j_gm_beams_z)
            delay(-self.p.t_diag_gm_beams_after_start)

    @kernel
    def lightsheet_load(self):
        """z frame t_diag_lightsheet_after_load after the cursor."""
        if self.active and self.j_lightsheet_load_z >= 0:
            delay(self.p.t_diag_lightsheet_after_load)
            self.cam_z.trigger(self.j_lightsheet_load_z)
            delay(-self.p.t_diag_lightsheet_after_load)

    @kernel
    def lightsheet_evap(self):
        """z frame t_diag_lightsheet_after_evap1 after the cursor."""
        if self.active and self.j_lightsheet_evap_z >= 0:
            delay(self.p.t_diag_lightsheet_after_evap1)
            self.cam_z.trigger(self.j_lightsheet_evap_z)
            delay(-self.p.t_diag_lightsheet_after_evap1)

    @kernel
    def tweezer_load(self):
        """x frame t_diag_tweezer_after_load after the cursor."""
        if self.active and self.j_tweezer_load_x >= 0:
            delay(self.p.t_diag_tweezer_after_load)
            self.cam_x.trigger(self.j_tweezer_load_x)
            delay(-self.p.t_diag_tweezer_after_load)

    @kernel
    def tweezer_evap(self):
        """x frame t_diag_tweezer_after_evap after the cursor."""
        if self.active and self.j_tweezer_evap_x >= 0:
            delay(self.p.t_diag_tweezer_after_evap)
            self.cam_x.trigger(self.j_tweezer_evap_x)
            delay(-self.p.t_diag_tweezer_after_evap)

    def finish(self):
        """Drain and close every stream (end_wax does this itself)."""
        for cs in self.streams.values():
            try:
                cs.finish()
            except Exception:
                pass
