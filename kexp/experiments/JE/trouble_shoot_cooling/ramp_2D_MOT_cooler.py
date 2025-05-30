from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_tof(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,camera_select='xy_basler',save_data=False)

        self.xvar('dummy',[0]*1000)

        self.n_steps = 1000

        # self.p.d2_2d_c_ramp_list = np.linspace(-3.,3.,self.n_steps)

        self.p.mot_current_ramp_list = np.linspace(1.,4.,self.n_steps)

        self.t_ramp = 4

        self.p.v_2d_mot_current = 3.5

        self.p.detune_d2_c_2dmot = -.6
        
        # self.p.amp_imaging = .17
        self.p.imaging_state = 2.
        # self.p.t_tof = 18.e-3
        self.p.t_mot_load = 0.1
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.switch_d2_2d(1)
        self.dds.push.off()

        self.dac.supply_current_2dmot.set(v=self.p.v_2d_mot_current)

        self.dds.d2_2dv_r.set_dds_gamma(delta=self.p.detune_d2_r_2dmot,
                                 amplitude=self.p.amp_d2_r_2dmot)
        delay(self.params.t_rtio)
        self.dds.d2_2dv_c.set_dds_gamma(delta=self.p.detune_d2_c_2dmot,
                                 amplitude=self.p.amp_d2_c_2dmot)
        delay(self.params.t_rtio)
        self.dds.d2_2dh_r.set_dds_gamma(delta=self.p.detune_d2_r_2dmot,
                                 amplitude=self.p.amp_d2_r_2dmot)
        delay(self.params.t_rtio)
        self.dds.d2_2dh_c.set_dds_gamma(delta=self.p.detune_d2_c_2dmot,
                                 amplitude=self.p.amp_d2_c_2dmot)

        # for g in self.p.d2_2d_c_ramp_list:
        #     self.dds.d2_2dv_c.set_dds_gamma(delta=g,
        #                             amplitude=self.p.amp_d2_c_2dmot)
        #     delay(self.params.t_rtio)
        #     self.dds.d2_2dh_c.set_dds_gamma(delta=g,
        #                             amplitude=self.p.amp_d2_c_2dmot)
        #     delay(self.t_ramp /self.n_steps)

        for v in self.p.mot_current_ramp_list:
            self.dac.supply_current_2dmot.set(v=v)
            delay(self.t_ramp /self.n_steps)

        delay(.25)
        self.switch_d2_2d(0)
        delay(.25)
       
    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)