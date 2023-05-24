from artiq.experiment import *
from artiq.experiment import delay, delay_mu
from kexp.config.dds_state import dds_state
import kexp.config.dds_id as dds_id
from kexp.config.expt_params import ExptParams
from kexp.base.base import Base

class Startup(EnvExperiment, Base):
    def build(self):
        '''
        Get core device, dds, zotino drivers.
        '''
        Base.__init__(self,setup_camera=False)

    @kernel
    def run(self):
        '''
        Init all devices, set dds to default values and turn on
        '''
        self.init_kernel()
        self.mot_observe()