from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from wax.config.config_dds import defaults as default_dds

class Startup(EnvExperiment):

    def read_dds_from_config(self):
        self.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        for dds0 in default_dds:
            dds0.dds_device = self.get_device(dds0.name())
            self.dds[dds0.urukul_idx][dds0.ch] = dds0

    @kernel
    def set_and_turn_on_dds(self):
        for dds_sublist in self.dds:
            for dds in dds_sublist:
                dds.set_dds()
                delay(10*us)

    @kernel
    def init_all_dds(self):
        for dds_sublist in self.dds:
            for dds in dds_sublist:
                dds.init_dds()

    def build(self):
        self.setattr_device("core")
        self.read_dds_from_config()

        self.setattr_device("zotino0")

    @kernel
    def run(self):
        self.core.reset()
        self.init_all_dds()
        self.set_and_turn_on_dds()
        self.zotino0.init()
        

    