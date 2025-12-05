from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from waxx.util.artiq.async_print import aprint

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=False,
                      imaging_type=img_types.ABSORPTION)

        self.p.t_xshim_rampdown = 20.e-3
        
        self.p.N_repeats = 100

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_shims(0.,0.,0.)

        delay(.5)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        self.dac.xshim_current_control.linear_ramp(t=20.e-3,v_start=0.,v_end=9.99,n=500)

        delay(20.e-3)

        # self.dac.xshim_current_control.linear_ramp(t=self.p.t_xshim_rampdown,
        #                                            v_start=9.99,
        #                                            v_end=self.p.v_x_shim_pol_contrast,
        #                                            n=100)
        
        delay(.25)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)