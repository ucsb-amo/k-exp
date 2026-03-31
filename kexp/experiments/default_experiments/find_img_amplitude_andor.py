from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class img_amp_calibration(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.xvar('amp_imaging',np.linspace(0.1,0.5,5))
        self.p.t_tof = 10.e-6
        self.p.N_repeats = 1
        self.p.t_mot_load = .25
        # self.p.v_pd_lightsheet_rampup_end = 4.16
        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
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