from artiq.experiment import *
from kexp.config.dds_state import defaults as default_dds

class Startup(EnvExperiment):

    def read_dds_from_config(self):
        '''
        Generate list of dds objects from defaults file, get device drivers for each
        '''
        self.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        for dds0 in default_dds:
            dds0.dds_device = self.get_device(dds0.name())
            self.dds[dds0.urukul_idx][dds0.ch] = dds0

    @kernel
    def set_and_turn_on_dds(self):
        '''
        Loops over list of dds objects, sets dds for each.
        '''
        for dds_sublist in self.dds:
            for dds in dds_sublist:
                dds.set_dds()
    @kernel
    def init_all_dds(self):
        '''
        Loops over list of dds objects, init dds (and cpld) for each.
        '''
        for dds_sublist in self.dds:
            for dds in dds_sublist:
                dds.init_dds()

    def build(self):
        '''
        Get core device, dds, zotino drivers.
        '''
        self.setattr_device("core")
        self.read_dds_from_config()
        self.setattr_device("zotino0")

    @kernel
    def run(self):
        '''
        Init all devices, set dds to default values and turn on
        '''
        self.core.reset()
        self.zotino0.init()
        self.init_all_dds()
        self.set_and_turn_on_dds()
        
    