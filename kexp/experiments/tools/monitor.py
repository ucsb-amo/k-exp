from artiq.experiment import *
from artiq.language.core import now_mu, delay

from kexp import Base

from waxx.util.artiq.async_print import aprint

# maybe liveOD runs this when an experiment is not running? It knows when experiments are running...

class testcrate_base(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare(shuffle=False)

    @kernel
    def run(self):
        self.init_kernel(run_id=False,
                         dds_off=False,
                         dds_set=False,
                         init_dac=True,
                         init_dds=True)
        
        self.monitor.monitor_loop(verbose=False)