from artiq.experiment import *
from artiq.language import delay, now_mu, TBool, TInt32, TFloat, kernel

from waxx.util.artiq.async_print import aprint

from kexp import Base, img_types, cameras
import numpy as np

class flimage_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      setup_camera=True)
        
        self.p.n_calibration_steps = 50
        self.p.n_samples_per_step = 100
        
        self.data.v = self.data.add_data_container(self.p.n_calibration_steps*self.p.n_samples_per_step)
        self.data.p = self.data.add_data_container(self.p.n_calibration_steps)
        
        self.finish_prepare(shuffle=False)
       
    @kernel
    def run(self):
        self.init_kernel(run_id = False,
                    init_dds =  False, 
                    init_dac = False,
                    dds_set = False, 
                    dds_off = False, 
                    init_imaging = True,
                    beat_ref_on= False,
                    init_shuttler = False, 
                    init_lightsheet = False,
                    setup_awg = False, 
                    setup_slm = False,
                    init_ry = False)
        
        self.scan()

    @kernel
    def scan_kernel(self):

        self.abs_image()

        self.ttl.imaging_shutter_x.on()
        self.imaging.set_power(1.5)

        self.imaging.on()

        wp = self.reference_arm_waveplate_pid

        wp.init(force_home=False)

        wp.find_pd_range(n_calibration_steps=self.p.n_calibration_steps,
                         N_samples_per_step=self.p.n_samples_per_step)
        
        self.data.p.put_data(wp._p_temp[0:wp.idx])
        self.data.v.put_data(wp._v_temp[0:wp.idx*self.p.n_samples_per_step])

    def analyze(self):

        self.reference_arm_waveplate_pid.close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)