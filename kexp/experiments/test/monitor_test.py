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
        self.init_kernel(run_id=False,init_lightsheet=False,setup_awg=False,setup_slm=False,dds_set=False,
                         dds_off=False,beat_ref_on=True,init_shuttler=False)
        # self.init_kernel(run_id=False,
        #                  init_dds=False,
        #                  init_dac=False,
        #                  dds_set=False,
        #                  dds_off=False)

        while True:
            self.core.wait_until_mu(now_mu())
            self.monitor.sync_change_list()
            self.core.break_realtime()
            self.monitor.apply_updates()
            delay(0.125*s)