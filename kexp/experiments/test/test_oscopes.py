from artiq.experiment import *
from artiq.language import now_mu
from kexp import Base, img_types, cameras

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=True,
                      save_data=True,
                      camera_select=cameras.andor)

        self.xvar('xv0',[1]*2)
        self.xvar('xv1',[1]*3)

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD')

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        # your sequence

        self.core.wait_until_mu(now_mu())
        self.scope.read_sweep(3)
        self.core.break_realtime()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)