from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)
        self.p = self.params

        self.p.f1 = 1.e6
        self.p.f2 = 2.e6
        self.p.f_list = np.linspace(self.p.f1,self.p.f2,100)
        self.p.t = 20.e-6
        dt = self.p.t / len(self.p.f_list)

        self.test_dds = self.dds.lightsheet

        self.dds.set_frequency_ramp_profile(self.test_dds,self.p.f_list,dt,dds_mgr_idx=0)

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        self.init_kernel()

        self.test_dds.set_dds(frequency=self.p.f1)

        self.dds.load_profile(dds_mgr_idx=0)

        self.dds.enable()

        self.trig_ttl.on()
        self.test_dds.on()
        delay(20.e-6)
        self.dds.commit_enable()
        # self.test_dds.set_dds(frequency=self.p.f_list[0])
        delay(self.p.t)
        self.dds.disable_profile()
        delay(5.e-6)
        self.test_dds.off()

        self.trig_ttl.off()