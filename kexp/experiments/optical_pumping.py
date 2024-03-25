from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler')
        # self.xvar('amp_optical_pumping_op',np.linspace(0.0,0.4,4))
        # self.xvar('amp_optical_pumping_r_op',np.linspace(0.0,0.4,4))
        
        # self.xvar('v_zshim_current_op',np.linspace(1.0,3.,4))


        # self.p.t_optical_pumping = 200.e-6
        t_max_us = 1000.
        self.xvar('t_optical_pumping',np.linspace(1.,t_max_us,20)*1.e-6)
        self.p.t_op_total = t_max_us * 1.e-6
        # t_max_ms = 10.
        # self.xvar('t_optical_pumping_bias_rampup',np.linspace(0.,t_max_ms,4)*1.e-3)
        # self.p.t_optical_pumping_bias_rampup_total = t_max_ms * 1.e-3

        # self.xvar('do_optical_pumping',[0,1])

        self.p.t_optical_pumping_bias_rampup = 1.e-3
        self.p.v_zshim_current_op = 2.
        self.p.t_mot_load = 1.

        self.p.imaging_state = 1.

        self.xvar('imaging_state',[1,2])

        # self.p.N_repeats = [1,1]

        self.finish_build()

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.break_realtime()

        if self.p.imaging_state == 1.:
            self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)
        else:
            self.set_imaging_detuning()

        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.release()
        self.flash_cooler()

        self.optical_pumping(t=self.p.t_optical_pumping,
                             t_bias_rampup=self.p.t_optical_pumping_bias_rampup)
        delay(self.p.t_op_total - self.p.t_optical_pumping)
        # delay(self.p.t_optical_pumping_bias_rampup_total - self.p.t_optical_pumping_bias_rampup)

        self.dds.power_down_cooling()

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        delay(self.p.t_lightsheet_hold)
        
        self.set_zshim_magnet_current()
        delay(15*ms)
        self.lightsheet.off()
        
        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
