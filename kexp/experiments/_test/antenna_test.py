from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
# from artiq.coredevice.adf5356 import ADF5356
# from artiq.coredevice.mirny import Mirny
import numpy as np

class antenna_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')

        self.p.t_mot_load = 1.
        self.p.t_tof = 20.e-6

        self.xvar('dummy',1.)

        self.finish_prepare()

    @kernel
    def scan_kernel(self):
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm, v_yshim_current=self.p.v_yshim_current_gm, v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)
        self.release()
        self.flash_cooler(t=1.e-3)
        self.ttl.antenna_rf_trig.pulse(100.e-6)
        self.release()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)


