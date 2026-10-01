"""BEC TOF loop: the experiment the Device Control GUI's "BEC TOF loop" card runs
back to back (the monitor server's run loop, waxx.util.device_state.run_loop).

High-field tweezer BEC (prepare_hf_tweezers), 100 ms hold, tweezer off, time of
flight, absorption image on the Andor. Each shot also starts with a 200 ms
2D-MOT-only pre-phase (push off) and snaps three auxiliary camera frames per
shot (2026-09-30): img_2dmot (2D MOT basler, late in the pre-phase), img_mot
(MOT basler, late in the 3D load) and img_mot_beams (xy_basler, 10 ms into the
3D load) -- see kexp.control.cameras.camera_stream. The t_tof scan
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
from kexp.control.cameras import camera_stream
from waxx.util.device_state.loop_scan import scan_from_env, values as scan_values


class auto_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.p.t_mot_load = 1.0
        self.p.t_tweezer_hold = 100.e-3
        # 2D-MOT-only pre-phase per shot (push off, 2D beams+current on):
        # gives the 2D MOT grab a clean moment before the 3D load starts.
        self.p.t_2dmot_prephase = 200.e-3

        # The loop hands over the scan set on its card (⚙); by hand: 2.5 ms x 15.
        scan = scan_from_env()
        if scan is None:
            self.xvar('t_tof', np.array([2.5e-3]))
            self.p.N_repeats = 15
        else:
            self.xvar('t_tof', scan_values(scan))
            self.p.N_repeats = scan['repeats']
            print(f"auto_tof: scan from the loop's settings: {scan}")

        # Aux cameras, one frame per shot each (settings + crop ROI from the
        # beacon server's saved defaults; 2026-09-30). xy_basler is snappable
        # because this run images on the Andor; if camera_select ever becomes
        # xy_basler, that grab degrades to a no-op dummy with a banner.
        # t_snap_lead from runs 84174/84175: snap fire->publish ~0.27-0.40 s
        # (2dmot), ~0.15 s (mot/xy).
        self.cam_2dmot = camera_stream(self, cameras.basler_2dmot,
                                       'img_2dmot', t_snap_lead=0.25)
        self.cam_mot = camera_stream(self, cameras.mot_basler, 'img_mot',
                                     t_snap_lead=0.15)
        self.cam_xy = camera_stream(self, cameras.xy_basler, 'img_mot_beams',
                                    t_snap_lead=0.15)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # Schedule this shot's aux-camera snaps (async RPC + host wall-clock;
        # offsets measured from the timeline cursor HERE, which is where the
        # pre-phase below starts; the 3D beams come on ~2 ms into mot()
        # inside prepare_hf_tweezers):
        #   2D MOT fluorescence, 50 ms into the pre-phase (its snap publishes
        #     ~+150 ms after target regardless of lead -- runs 84174/84175 --
        #     so the early target keeps the exposure inside the pre-phase);
        #   MOT-beam light on xy_basler, 100 ms before the 3D load ends
        #     (at +10 ms after load start the frames are ALL ZERO at the
        #     saved 19 us / 0 dB settings -- run 84174; late in the load the
        #     beam/fluorescence signal is strong -- run 84175);
        #   MOT fluorescence, 150 ms before the 3D load ends (its exposure
        #     publishes ~+110+-20 ms late; at -100 ms one of 15 shots in run
        #     84176 exposed just after the load ended and came back dark --
        #     -150 ms leaves ~65 ms of margin).
        self.cam_2dmot.grab(50.e-3)
        self.cam_xy.grab(self.p.t_2dmot_prephase + 2.e-3
                         + self.p.t_mot_load - 100.e-3)
        self.cam_mot.grab(self.p.t_2dmot_prephase + 2.e-3
                          + 50e-3)

        self.load_2D_mot(self.p.t_2dmot_prephase, with_push=False)

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
