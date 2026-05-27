from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
from kexp.base.cameras import img_config

class turn_on_imaging(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      suppress_live_od=True)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        
        self.prep_raman()
        self.raman.dds_sw.set_dds(amplitude=0.05)
        self.raman.on()
    
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)