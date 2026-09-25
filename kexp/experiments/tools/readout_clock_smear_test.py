"""Andor readout-clock check: image the probe beam, no atoms.

Purpose
-------
The 2026-09-23 dark-frame sweep suggested moving the Andor vertical clock
from 0.5 us / +3 to 0.3 us / Normal amplitude because its dark-frame event
count was ~70x lower. Runs 80707 (0.5 us / +3) vs 80708 (0.3 us / Normal)
with this experiment showed why: at 0.3 us / Normal the light frames hold
no image at all (charge is not transferred), so the low dark count was
signal loss, not low CIC. camera_id was reverted to 0.5 us / +3. A dark
frame cannot show this; only a real signal can. This experiment takes the
ordinary absorption frame
sequence (light, light, dark) with the probe beam on and no atoms, at the
same 30 ms frame gaps the real sequence now uses, so the saved frames test
both the clock setting and the shortened gaps.

Run once with each camera setting you want to compare. The clock settings
are applied when liveOD opens the camera, so:

  1. Set vs_speed / vs_amp in kexp.config.camera_id.
  2. Restart the LiveOD server on kong so CameraNanny reopens the Andor.
  3. `ar andor_readout_smear_test.py`
  4. Repeat for the other setting.

The HDF5 records camera_params, so each run labels itself.

What to look at (per run, in a notebook)
----------------------------------------
    from kexp import atomdata
    import numpy as np, matplotlib.pyplot as plt
    ad = atomdata(RUN_ID, roi_id='auto')
    light = ad.img_light.astype(float)          # (N, 512, 512)
    dark  = ad.img_dark.astype(float)
    sig   = light.mean(0) - dark.mean(0)

    # 1. vertical profile of the beam, column-summed.  A charge-transfer
    #    defect appears as a one-sided tail along the vertical (readout)
    #    axis; the horizontal profile is the control.
    vprof = sig.sum(1); hprof = sig.sum(0)
    plt.figure(); plt.semilogy(vprof/vprof.max(), label='vertical (shift axis)')
    plt.semilogy(hprof/hprof.max(), label='horizontal'); plt.legend()
    plt.title(f'run {ad.run_info.run_id}  |  vs_speed={ad.camera_params.vs_speed} '
              f'vs_amp={ad.camera_params.vs_amp}')

    # 2. skewness of the vertical profile: ~0 for a symmetric beam, grows
    #    with a smear tail.  Compare between the two runs.
    y = np.arange(512); w = np.clip(vprof, 0, None); w /= w.sum()
    m = (y*w).sum(); s = np.sqrt(((y-m)**2*w).sum())
    print('vertical skew', ((y-m)**3*w).sum()/s**3)

    # 3. frame-to-frame reproducibility and dark-frame event rate
    print('light frame rms/mean', light.std(0).mean()/light.mean())
    print('dark bias', dark.mean(), ' dark events/pix/frame',
          (dark > np.median(dark) + 6*1.4826*np.median(np.abs(dark-np.median(dark)))).mean())

Data on disk is read-only; this run is a diagnostic and is analysed in a
notebook, not written back anywhere.
"""

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np


class andor_readout_smear_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select='andor',
                      imaging_type=img_types.ABSORPTION)

        # probe power is the ordinary absorption setting: camera_params.amp_imaging,
        # applied by init_kernel / reset_devices through the imaging PID.

        # Vertical-clock override for A/B comparison. liveOD opens the camera
        # with the camera_params this experiment sends at INIT_RUN, so setting
        # them here is enough; camera_id.py is untouched and the run file
        # records the values used. None = use camera_id (the new setting).
        # NOTE: before 2026-09-24 liveOD applied vs_speed/vs_amp only when it first
        # opened the camera, so runs 80702-80706 all ran at one clock whatever
        # their camera_params say. camera_nanny.update_params now reapplies them.
        # VS_OVERRIDE = (1, 3)   # old setting: 0.5 us shift, +3 amplitude (run 80702, run 80707)
        VS_OVERRIDE = None       # new setting from camera_id: 0.3 us shift, Normal (run G)
        if VS_OVERRIDE is not None:
            self.camera_params.vs_speed, self.camera_params.vs_amp = VS_OVERRIDE

        # Baseline-clamp A/B (2026-09-24). Clamp on is the default since the
        # camera constructor change of 2026-09-23; None = leave the default.
        # CLAMP_OVERRIDE = 0     # clamp off: run 80709, bias 1725 ADU drifting 1829->1680 over 20 shots
        CLAMP_OVERRIDE = None    # default (on): run 80707, bias 522.7 +/- 2.2 ADU frame to frame
        if CLAMP_OVERRIDE is not None:
            self.camera_params.baseline_clamp = CLAMP_OVERRIDE

        # one dummy scan variable so the scan loop runs N times
        self.p.dummy = 0.
        self.xvar('dummy', np.zeros(20))   # runs 80702, 80703, and the beams-off run

        # Dark-gap scan (2026-09-24): dark frames in 80702/80703 carried light
        # (median ~4500 ADU vs 522 in a real run) with a gradient along the
        # shift axis, i.e. light during the dark-frame readout. Scan the delay
        # between close_imaging_shutters and the dark trigger to find the
        # shutter closing time. The light gap stays at camera_params value.
        self.p.t_dark_gap = self.camera_params.t_dark_image_delay
        # self.xvar('t_dark_gap', np.arange(20.e-3, 81.e-3, 10.e-3))  # run 80704: 20 ms < camera
        #   ready floor (18.1 ms readout + 3.9 ms keep-clean), 3 dark triggers dropped, grab timed out
        # self.xvar('t_dark_gap', np.array([25., 30., 40., 50., 60., 70., 80.]) * 1.e-3)  # run 80705:
        #   dark contamination independent of gap 30-80 ms -> not the shutter
        # self.p.N_repeats = 3

        # Beams-off test (2026-09-24): the per-shot reset (reset_devices) turns
        # the 2D MOT and push beams on and this test never turned them off, so
        # continuous near-resonant light may be what reaches the sensor during
        # readout. power_down_cooling() in scan_kernel switches all of it off
        # (imaging beam untouched), as a real sequence does before imaging.
        self.p.beams_off_before_imaging = 1.

        # settle time after (re)opening the imaging shutters
        self.p.t_shutter_settle = 100.e-3

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        # turn off every near-resonant cooling beam (2D MOT, push, 3D MOT, OP,
        # ...) that reset_devices switched on at the start of the shot; the
        # imaging beam is left alone. Standard helper used before imaging in
        # real sequences.
        if self.p.beams_off_before_imaging > 0.5:
            self.power_down_cooling()
        self.set_imaging_shutters()
        delay(self.p.t_shutter_settle)

        # "atoms" frame: beam only
        self.light_image()

        # light frame, at the real light-only gap
        delay(self.camera_params.t_light_only_image_delay)
        self.light_image()

        # dark frame, at the real dark gap
        self.close_imaging_shutters()
        delay(self.p.t_dark_gap)
        self.dark_image()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False, setup_slm=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
