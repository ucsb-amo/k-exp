from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class img_detuning(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.

        self.xvar('frequency_detuned_imaging',np.arange(40.,100.,2)*1.e6)

        self.p.t_tof = 10.e-3

        self.p.N_repeats = 3

        self.p.t_mot_load = .05

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)

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