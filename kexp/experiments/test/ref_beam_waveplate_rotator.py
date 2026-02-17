from artiq.experiment import *
from artiq.language import delay, now_mu, TBool, TInt32, TFloat, kernel

from waxx.util.artiq.async_print import aprint

from kexp import Base, img_types, cameras
import numpy as np

class flimage_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False)
        
        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(run_id = False,
                    init_dds =  False, 
                    init_dac = False,
                    dds_set = False, 
                    dds_off = False, 
                    init_imaging = False,
                    beat_ref_on= False,
                    init_shuttler = False, 
                    init_lightsheet = False,
                    setup_awg = False, 
                    setup_slm = False,
                    init_ry = False)

        self.reference_arm_waveplate_pid.init(force_home=False)
        
        # self.reference_arm_waveplate_pid.move_by(10000)
        # while self.reference_arm_waveplate_pid.is_moving():
        #     pass
        pos = self.reference_arm_waveplate_pid.get_position()
        print(pos)

        # delay(100.e-3)
        # v = self.reference_arm_waveplate_pid.sampler_ch.sample()
        # delay(100.e-3)
        # aprint(v)
        self.reference_arm_waveplate_pid.find_pd_range(n_calibration_steps=100)

    # def analyze(self):
        # import os
        # expt_filepath = os.path.abspath(__file__)
        # self.end(expt_filepath)