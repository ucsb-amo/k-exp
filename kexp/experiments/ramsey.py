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

        # self.xvar('frequency_raman_transition',41.1*1e6 + np.linspace(-0.1e6, 0.1e6,5))

        # self.xvar('amp_raman',np.linspace(0.12,.35,5))

        # self.xvar('t_raman_pulse',np.linspace(0.,300.,100)*1.e-6)

        # self.xvar('t_ramsey_delay',np.linspace(0.,50.,25)*1.e-6)
        self.p.t_ramsey_delay = 20.e-6

        # self.xvar('t_tweezer_hold',np.linspace(0.,1.5,10)*1.e-3)
        self.p.t_tweezer_hold = .1e-3

        self.xvar('global_phase_shift',np.linspace(0.,np.pi,3))
        self.p.global_phase_shift = 0.

        self.p.t_mot_load = 1.
        self.p.t_tof = 300.e-6
        self.p.N_repeats = 15

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)

        self.prepare_lf_tweezers()

        self.init_raman_beams()
        
        self.raman.pulse(self.p.t_raman_pi_pulse/2)

        self.raman.set_phase(global_phase=self.p.global_phase_shift)
        delay(self.p.t_ramsey_delay)

        self.raman.pulse(self.p.t_raman_pi_pulse/2)

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