from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
from kexp.base.cameras import img_config

class turn_on_imaging(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=False,
                      suppress_live_od=True)

        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(dds_off=False,
                         dds_set=False,
                         init_dds=False,
                         setup_awg=False,
                         setup_slm=False,
                         init_lightsheet=False,
                         init_shuttler=False)
        
        self.inner_coil.on()
        self.inner_coil.set_voltage(20.)
        self.inner_coil.set_supply(self.p.i_magtrap_init)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)