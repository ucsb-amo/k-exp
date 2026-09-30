"""BEC TOF loop: the experiment the Device Control GUI's "BEC TOF loop" card runs
back to back (the monitor server's run loop, waxx.util.device_state.run_loop).

High-field tweezer BEC (prepare_hf_tweezers), 100 ms hold, tweezer off, time of
flight, absorption image on the Andor, after 2 warm-up shots. The t_tof scan
and repeats come from the loop card's settings (⚙; the monitor server passes
them in WAXX_LOOP_SCAN); run by hand, t_tof is 2.5 ms, 15 repeats, shuffled. The saved xvars and N_repeats are what a run actually used.

A copy of default_experiments/hf_tweezer_bec.py made for the loop on
2026-09-26, and deliberately independent of it: edit this file only to change
what the loop measures. No run-done email (a loop would send one per run) and
no monitor restart between runs; pressing Stop on the card lets the current
run finish and then restarts the monitor. Run by hand, it leaves the monitor
stopped.
"""

import numpy as np
from artiq.experiment import *
from kexp import Base, img_types, cameras
from waxx.util.device_state.loop_scan import scan_from_env, values as scan_values


class auto_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=2)

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3

        # The loop hands over the scan set on its card (⚙); by hand: 2.5 ms x 15.
        scan = scan_from_env()
        if scan is None:
            self.xvar('t_tof', np.array([2.5e-3]))
            self.p.N_repeats = 15
        else:
            self.xvar('t_tof', scan_values(scan))
            self.p.N_repeats = scan['repeats']
            print(f"auto_tof: scan from the loop's settings: {scan}")

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.prepare_hf_tweezers()
        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.ttl.pd_scope_trig3.pulse(1.e-6)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__), notify=False, restart_monitor=False)
