from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class rabi_oscillation(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.frequency_raman_transition = 155.e6

        self.xvar('t_raman_pulse',np.linspace(0.,2.,3)*1.e-3)
        self.p.t_raman_pulse = 0.

        self.p.t_tof = 20.e-6
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()
        self.prep_raman()
        
        self.raman.pulse(self.p.t_raman_pulse)

        self.ttl.raman_shutter.off()

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
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)