from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class mot_killa(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        self.xvar('t_ramp',np.linspace(10.,1000.,6)*1.e-3)

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,setup_slm=False,
                         init_dds=False,beat_ref_on=False,
                         dds_off=False,init_lightsheet=False,
                         init_shuttler=False)
        self.outer_coil.on()
        self.outer_coil.set_voltage(20.)
        delay(30.e-3)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.ramp_supply(self.p.t_ramp,
                                    0.,100.,1000)
        delay(30.e-3)
        self.outer_coil.off()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)