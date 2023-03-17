from artiq.experiment import *
from kexp.config.dds_state import dds_state
import kexp.config.dds_id as dds_id
from kexp.config.expt_params import ExptParams

class Startup(EnvExperiment):
    def build(self):
        '''
        Get core device, dds, zotino drivers.
        '''
        self.setattr_device("core")

        self.dds = dds_id.dds_frame(dds_state)
        self.dds.get_dds_devices(self)

        self.setattr_device("zotino0")

        self.dds_list = self.dds.dds_list()

        self.params = ExptParams()

    @kernel
    def run(self):
        '''
        Init all devices, set dds to default values and turn on
        '''
        self.core.reset()
        self.zotino0.init()
        for dds in self.dds_list:
            dds.init_dds()
            dds.set_dds()
        delay(1*us)
        self.zotino0.write_dac(0,self.params.V_mot_current)
        self.zotino0.load()
        
    