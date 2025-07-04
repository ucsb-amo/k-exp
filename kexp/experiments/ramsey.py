from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class ramsey(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        ### 
        # self.xvar('frequency_raman_transition',41.289e6 + np.linspace(-15.e3,15.e3,7))
        self.p.t_ramsey = 10.e-6
        df = 100.e3
        self.p.frequency_raman_transition_detuned = self.p.frequency_raman_transition + df
        T = 1./df
        dt = T / 10
        N_T = 4
        self.xvar('t_ramsey',np.arange(0.,N_T*T+dt,dt))

        # self.p.t_raman_pulse = 0.
        # self.p.amp_raman  = 0.25

        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]
        self.p.t_mot_load = 1.
        self.p.t_tof = 300.e-6
        self.p.N_repeats = 15

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)

        self.prepare_lf_tweezers()

        self.init_raman_beams()
        
        self.pi_pulse()

        self.raman.set_transition_frequency(self.p.frequency_raman_transition_detuned)

        self.hadamard()
        delay(self.p.t_ramsey)
        self.hadamard()
        
        self.tweezer.off()

        delay(self.p.t_tof)
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