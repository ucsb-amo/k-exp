from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
from kexp.base.cameras import img_config

class turn_on_imaging(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=False)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        
        self.init_raman_beams_nf(frequency_transition=460.e6,fraction_power=1.0)
        self.raman_nf.on()
    
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)