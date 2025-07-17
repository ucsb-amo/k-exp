from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(440.,480.,3)*1.e6)

        # self.xvar('detune_push',np.linspace(-5.,2.,20))
        # self.xvar('amp_push',np.linspace(.05,.188,8))
        # self.p.detune_push = 0.

        # self.xvar('detune_d2v_c_2dmot',np.linspace(-4.,0.,8))
        # self.xvar('detune_d2h_c_2dmot',np.linspace(-4.,0.,8))
        # self.xvar('detune_d2v_r_2dmot',np.linspace(-7.,-2.,8))
        # self.xvar('detune_d2h_r_2dmot',np.linspace(-7.,-2.,8))
        # self.p.detune_d2_r_2dmot = -4.4
        # self.p.detune_d2_c_2dmot = -1.6

        # self.xvar('amp_d2_c_2dmot',np.linspace(-6.,0.,8))
        # self.xvar('amp_d2_r_2dmot',np.linspace(.1,.188,8))

        # self.xvar('t_tof',np.linspace(50.,500.,10)*1.e-6)
        
        self.p.imaging_state = 2.
        self.p.t_tof = 300.e-6
        self.p.t_mot_load = .3
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.load_2D_mot(self.p.t_2D_mot_load_delay)

        self.mot(self.p.t_mot_load)
        self.dds.push.off()

        self.release()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
       
    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)