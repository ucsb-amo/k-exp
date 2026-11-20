from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
from kexp.control.cameras.camera_stream import camera_stream
import numpy as np


class diag_gm_frame_timing(EnvExperiment, Base):
    """Where to put the GM diagnostic frame (diagnostic_frame.img_gm) on the
    MOT Basler: scans the trigger edge across the cooling sequence (2026-11-19).

    The MOT Basler (a2A3840-45um) is a rolling-shutter camera: sensor row r
    starts its exposure ~ d + r * tau after the edge and integrates for the
    exposure time T. img_gm is triggered t_offset = -25 ms from GM start
    (#84561, 2026-10-01) at T = 3 ms / 30 dB, chosen before the row timing
    was measured. This run measures it.

    Timeline, relative to GM start (t = 0, the cursor at the end of
    cmot_d1, where cooling.cmot_d1 calls self.diag.img_gm.trigger()):

        ... -10 ms   MOT (D2 cooler + repump; bright)
        -10 .. 0     D1-CMOT  (D1 cooler, D2 repump)        t_d1cmot = 10 ms
          0 .. 3     GM       (D1 cooler + D1 repump)       t_gm     =  3 ms
          3 .. 9     GM ramp  (D1 power ramped down)        t_gmramp =  6 ms
          9          release(): D1/D2 off, IGBT off -- no light after this
          9 + t_tof  repump flash + xy absorption image

    One frame per shot: the edge at p.t_gm_frame_offset from GM start
    (scanned), the full sensor stored block-averaged 4 x 4. Each row band's
    brightness vs edge time is a staircase (MOT -> D1-CMOT -> GM -> ramp ->
    dark) shifted by the row's own delay, so the light-off edge (+9 ms) and the
    MOT-end edge (-10 ms) give tau and d, and the offset that puts the
    cloud's rows inside GM. Analysis: analyze_gm_frame_timing.py in the
    run's skynet_log outputs folder.

    Differences from a real (diagnostics-on) run, on purpose:
      - diagnostic_images=False: the MOT Basler stream is this run's own.
        mot() then skips the 2D-MOT-only pre-phase (push off ~148 ms before
        the 3D MOT comes on); that changes the load, not the GM timing.
      - release() after the GM ramp, as gm_tof.py; the real sequence goes to
        start_magtrap(), whose pump_to_F1 light comes right after +9 ms.
      - t_tof = 100 ms: the repump flash and absorption pulses (~+109 ms) come
        after every row's exposure at every scanned edge (the longest is
        ~+16 + 48 + 3 ms if the full sensor reads out in ~48 ms; wiki /
        camera_id). The xy absorption image is then of an empty region; it is
        here only because a saving run needs a run camera.
    """

    def prepare(self):
        Base.__init__(self, setup_camera=True, save_data=True,
                      camera_select=cameras.xy_basler,
                      imaging_type=img_types.ABSORPTION,
                      diagnostic_images=False,
                      warmup_shots=3)

        # the GM frame as diagnostic_frame.img_gm takes it (camera_id.py):
        # 3 ms / 30 dB; full sensor, block-averaged 4 x 4 (rows: ~4 x tau each)
        self.gm_cam = camera_stream(self, cameras.mot_basler, 'img_gm_timing',
                                    mode='triggered',
                                    exposure_time=3.e-3, gain=30.,
                                    crop_to_saved_roi=False,
                                    no_roi_downsample=4)

        self.p.imaging_state = 2.
        self.p.t_tof = 100.e-3

        # edge time from GM start; img_gm today: -25 ms
        self.p.t_gm_frame_offset = -25.e-3
        self.xvar('t_gm_frame_offset', np.arange(-60., 16.1, 2.) * 1.e-3)   # 39 points
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.imaging.set_power(self.camera_params.amp_imaging)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)

        # cursor = GM start; the edge goes t_gm_frame_offset from here (the
        # stream fires it its exposure delay early, as img_gm.trigger() does)
        delay(self.p.t_gm_frame_offset)
        self.gm_cam.trigger(0)
        delay(-self.p.t_gm_frame_offset)

        self.gm(self.p.t_gm)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        delay(self.p.t_tof)

        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
