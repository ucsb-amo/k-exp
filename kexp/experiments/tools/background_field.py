from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types

class background_field(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=False)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(True,
                         False,
                         True,
                         False,
                         False,
                         False,
                         False,
                         True,
                         False,
                         False,
                         False,
                         False,
                         False,
                         False)
        
        self.background_field()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)