from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class trap_frequency_parametric_amp_mod(EnvExperiment, Base):
    """Parametric heating via sinusoidal modulation of the AWG DDS amplitude
    (i.e. the tweezer RF power) of a single trap. Resonance is expected at
    2*f_trap (and at f_trap for a trap displaced from the modulation center).

    Companion to trap_frequency.py / trap_frequency_parametric_thermal.py,
    which shake the trap position instead.
    """

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 1500.e-6

        self.p.t_tweezer_amp_mod = 100.e-3
        # linear ramp-in of the modulation depth (0. for an abrupt start)
        self.p.t_tweezer_amp_mod_ramp = 0.

        # fractional DDS amplitude modulation depth; optical power depth ~ 2x
        self.p.amp_tweezer_mod_depth = 0.05

        # position-shake resonance was scanned 0.59-0.85 kHz; parametric
        # resonance from amplitude modulation is expected near 2*f_trap
        self.xvar('f_tweezer_amp_mod',np.linspace(1.0,2.0,11)*1.e3)
        # self.p.f_tweezer_amp_mod = 1.4e3

        self.p.amp_imaging = .2
        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # arm the modulation on the AWG; it starts on the next AWG trigger
        self.tweezer.sine_amplitude_modulation(tweezer_idx=0,
                            t_mod=self.p.t_tweezer_amp_mod,
                            amp_mod_depth=self.p.amp_tweezer_mod_depth,
                            f_mod=self.p.f_tweezer_amp_mod,
                            t_amod_ramp=self.p.t_tweezer_amp_mod_ramp,
                            trigger=False)
        delay(100.e-3)

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        # don't quite evap to BEC
        self.prepare_hf_tweezers(do_tweezer_evap_2=False,
                                squeeze=False,
                                ramp_down_painting=False)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_amp_mod)
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
