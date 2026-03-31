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
        
        
        df = 10.e6
        # self.xvar('frequency_detuned_from_free_space_resonance', df * np.linspace(-1.,1.,20))
        self.p.frequency_detuned_from_free_space_resonance = -3.684e6

        # self.xvar('v_pd_hf_tweezer_squeeze_power',np.linspace(0.,6.,10))

        self.p.t_tof = 20.e-6
        self.p.N_repeats = 5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        f = self.p.frequency_detuned_hf_f1m1 + self.p.frequency_detuned_from_free_space_resonance
        self.set_imaging_detuning(frequency_detuned=f)
        self.imaging.set_power(self.camera_params.amp_imaging)

        self.prepare_hf_tweezers()

        delay(self.p.t_tof)
        self.abs_image_in_trap()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)