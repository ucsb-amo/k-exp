"""
Warm-up dry-run test for the hf BEC sequence.

Runs the same sequence as default_experiments/hf_tweezer_bec.py (2026-09-08
version, same in-file parameter overrides) as N_repeats identical shots at a
fixed TOF -- no scanned parameter.

The one addition is the opt-in warm-up now built into Base: passing
warmup_shots=N to Base.__init__ makes Base.pre_scan() run N complete BEC
preparations (Cooling.warmup_kernel) with no imaging before the first real
shot. Warm-up shots never trigger the camera, never write to the DataVault,
and never notify liveOD, so the saved run looks exactly like a plain N_repeats
run. Set warmup_shots=0 to reproduce the plain experiment for comparison.

Motivation: the first shot of every hf_bec run is ~25% low in atom number
(runs 78510-78570, 2026-09-08; probe intensity on shot 1 is normal, so the loss
is real). Results: warmup_shots=2 -> shot 1 at 0.92 of the rest (run 78568),
warmup_shots=7 -> 0.99 (78569), warmup_shots=0 -> 0.77 (78570).
"""

import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras


class hf_bec_warmup_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=5)

        # --- overrides carried over from hf_tweezer_bec.py (2026-09-08) ---
        self.p.t_mot_load = 1.0
        self.p.t_imaging_pulse = 10.e-6
        self.p.t_tweezer_hold = 100.e-3
        self.p.t_tof = 3.e-3

        self.p.v_hf_tweezer_paint_amp_max = 1.35
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 2.75
        self.p.v_pd_lightsheet_rampdown3_end = 0.06
        self.p.v_pd_hf_lightsheet_rampdown_end = 0.45
        self.p.t_hf_tweezer_1064_rampdown = 600.e-3

        self.p.N_repeats = 11

        self.finish_prepare(shuffle=True)

    # ------------------------------------------------------------------
    # the real shot -- identical to hf_tweezer_bec.py
    # ------------------------------------------------------------------

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers()

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()
        self.lightsheet.off()

        delay(self.p.t_tof)

        delay(20.e-6)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
