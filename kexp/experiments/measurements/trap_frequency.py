from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class trap_frequency(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.t_tof = 100.e-6

        # self.xvar('t_tweezer_mod',np.linspace(1.,5.,10)*1.e-3)
        self.p.t_tweezer_mod = 15.e-3

        # self.p.v_pd_tweezer_1064_ramp_end = 4.
        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(2.,8.7,8))

        self.xvar('f_tweezer_mod',np.linspace(.5e3,10.e3,20))
        self.p.f_tweezer_mod = 500.
        self.p.x_tweezer_mod_amp = .125e-6 # ~51kHz mod depth on AOD tone (2025-05-15)

        self.p.N_repeats = 2
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.trap.sine_move(t_mod=self.p.t_tweezer_mod,
                            x_mod=self.p.x_tweezer_mod_amp,
                            f_mod=self.p.f_tweezer_mod,
                            trigger=False)
        delay(100.e-3)
        
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(squeeze=True)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_mod)
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