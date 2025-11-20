from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class inner_coil_off_pretrigger(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.p.t_helmholtz_off = 220.e-6
        # self.xvar('t_helmholtz_off',np.linspace(0.,300.,10)*1.e-6)

        self.p.N_repeats = 5

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.cmot_d1(self.p.t_d1cmot)

        delay(-self.p.t_helmholtz_off)
        self.inner_coil.igbt_ttl.off()
        delay(self.p.t_helmholtz_off)

        self.ttl.pd_scope_trig.pulse(1.e-8)
        self.gm(self.p.t_gm)
        self.gm_ramp(self.p.t_gmramp)

        self.release()

        delay(self.p.t_tof)

        # self.flash_repump()
        # self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_shuttler=False,
                         init_lightsheet=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
