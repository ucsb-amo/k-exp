from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class img_amp_calibration(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        self.xvar('amp_imaging',np.linspace(0.1,0.5,10))
        self.p.t_tof = 14.e-3
        self.p.N_repeats = 3
        self.p.t_mot_load = .1
        self.finish_prepare(shuffle=True)

        self.camera_params.amp_imaging

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(amp=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.gm(self.p.t_gm * s)
        self.ttl.pd_scope_trig.on()
        self.gm_ramp(self.p.t_gmramp)
        self.ttl.pd_scope_trig.off()

        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
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