from artiq.experiment import *
from artiq.experiment import delay
from artiq.language.core import now_mu
from kexp import Base
import numpy as np

class magnet_ramp(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        # self.xvar('t_ramp',np.linspace(100.,500.,1)*1.e-3)
        self.p.t_ramp = 500.e-3
        # self.xvar('n_ramp', np.linspace(3,30,4))
        self.p.n_ramp = 100

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.core.wait_until_mu(now_mu())
        print(self.p.t_ramp)
        delay(5.e-3)

        self.outer_coil.on()
        self.outer_coil.set_voltage(20.)
        delay(30.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.ramp_supply(self.p.t_ramp,
                                    0.,100.,int(self.p.n_ramp))
        delay(30.e-3)
        self.outer_coil.off()

        delay(0.8)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,setup_slm=False,
                         init_dds=False,beat_ref_on=False,
                         dds_off=False,init_lightsheet=False,
                         init_shuttler=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)