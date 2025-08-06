from kexp.util.device_state.update_state_file import update_state_from_base
from kexp.util.device_state.sync_hardware_to_config import DeviceStateUpdater
from kexp import Base

from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from artiq.language.core import now_mu

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)

        print(self.config_file)
        
        self.finish_prepare(verbose=False)

    @kernel
    def run(self):
        self.init_kernel(run_id=False,
                         setup_awg=False,setup_slm=False,
                         dds_off=False,init_dds=False,
                         init_shuttler=False,
                         init_lightsheet=False)
        
        # self.start_monitoring()
        
        for _ in range(100):
            
            self.core.wait_until_mu(now_mu())
            delay(1.)
            self.check_and_update_devices(verbose=True)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
        update_state_from_base(self)