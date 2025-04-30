from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM

# SLM.write_phase_spot(100e-6,3.14,960,200)
class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select='andor',
                      imaging_type=img_types.ABSORPTION)


        
        self.xvar('px_slm_phase_spot_position_y',np.linspace(600,1200,10,dtype=int))
        self.p.phase_slm_spot = 3.14
        self.p.diameter_slm_spot = 100e-6
        # self.p.px_slm_phase_spot_position_y = 800
        self.p.amp_imaging = .35
        self.p.N_repeats = 1
        self.finish_prepare(shuffle=True)
    
        

    @kernel
    def scan_kernel(self):
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.slm.write_phase_spot()

        delay(5.)
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        
        self.scan()

        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)