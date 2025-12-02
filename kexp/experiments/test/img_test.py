from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np

class test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      imaging_type=img_types.ABSORPTION,
                      setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=False)
        
        self.xvar('dummy',[1]*1)

        # self.xvar('v_pd_img',np.linspace(0.1,6.25,8))
        self.p.v_pd_img = 0.11

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.imaging.set_power(self.p.v_pd_img)
        delay(10.e-3)

        self.imaging.ttl_pid_manual_override.on()
        self.imaging.dds_pid.set_dds(amplitude=0.086)

        delay(10.e-3)

        self.ttl.pd_scope_trig.pulse(1.e-8)
        self.imaging.on()
        delay(600.e-6)
        self.imaging.off()

        delay(10.e-3)

        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel()
        # self.load_2D_mot(self.p.t_2D_mot_load_delay)f
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)