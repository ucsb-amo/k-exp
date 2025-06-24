from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from artiq.language.core import now_mu, at_mu

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class rabi_oscillations(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.N_repeats = 1
        self.p.N_pwa_per_shot = 1

        ### Experiment setup
        
        # self.xvar('t_raman_pulse',np.arange(0.,2*N,0.25)*self.p.t_raman_pi_pulse)
        # self.xvar('t_raman_pulse',np.linspace(0.,5.e-6,10))
        # self.xvar('t_raman_pulse',)
        # self.p.t_raman_pulse = 0.
        self.tf = 2.e-3
        # self.xvar('t_raman_pulse',np.concatenate([np.linspace(0.,3.e-6,9),[self.tf]]))
        t_pi = 2.6137e-06
        N = 4
        # self.xvar('t_raman_pulse',np.arange(0.,2*N,0.5)*t_pi)
        self.xvar('t_raman_pulse',np.linspace(0.,500.e-6,1))

        # speed mode saves like 3 seconds per shot, doubles data rate
        # self.p.t_magtrap = 1.
        # self.p.t_magtrap_ramp = 0.25
        # self.p.t_lightsheet_rampup = 0.5
        # self.p.t_lightsheet_rampdown = 0.25

        ### misc params ###
        self.p.t_tof = 300.e-6
        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]

        self.finish_prepare(shuffle=True)

    @kernel
    def set_up_imaging(self):
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_m1)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)

    @kernel
    def scan_kernel(self):

        self.set_up_imaging()
        self.prepare_lf_tweezers()
        self.init_raman_beams()
        
        # if self.p.t_raman_pulse == self.tf:
        f = 38.e6
        # else:
        # f = self.p.frequency_raman_transition

        self.raman.pulse(self.p.t_raman_pulse,f)
        delay(1.e-3)
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