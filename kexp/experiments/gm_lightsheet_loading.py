from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class gm_lightsheet_loading(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.detune_d1_c_gmls = self.p.detune_d1_c_gm
        self.p.detune_d1_r_gmls = self.p.detune_d1_r_gm
        self.p.v_pd_d1_c_gmls = self.p.v_pd_d1_c_gm
        self.p.v_pd_d1_r_gmls = self.p.v_pd_d1_c_gm

        self.p.do_gm_ls = 1.

        # self.p.t_gm_lightsheet = 1.

        self.xvar('do_gm_ls',[0.,1.])

        self.p.t_mot_load = 0.3
        self.p.t_tof = 800.e-6
        self.p.N_repeats = 3
        self.finish_prepare(shuffle=True)

    @kernel
    def gm_ls_setup(self):
        if self.p.do_gm_ls:
            self.dds.d1_3d_c.set_dds_gamma(delta=self.p.detune_d1_c_gmls,
                                           amplitude=self.p.amp_d1_3d_c,
                                           v_pd=self.p.v_pd_d1_c_gmls)
            self.dds.d1_3d_r.set_dds_gamma(delta=self.p.detune_d1_r_gmls,
                                           amplitude=self.p.amp_d1_3d_r,
                                           v_pd=self.p.v_pd_d1_r_gmls)

    @kernel
    def gm_ls_on(self):
        if self.p.do_gm_ls:
            self.dds.d1_3d_c.on()
            self.dds.d1_3d_r.on()

    @kernel
    def gm_ls_off(self):
        if self.p.do_gm_ls:
            self.dds.d1_3d_c.off()
            self.dds.d1_3d_r.off()

            self.dds.d1_3d_r.set_dds(amplitude=0.)
            self.dds.d1_3d_c.set_dds(amplitude=0.)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.pump_to_F1()
        self.dds.power_down_cooling()

        self.inner_coil.on()
        self.gm_ls_setup()

        self.gm_ls_on()
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
        self.gm_ls_off()
        
        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)
        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.)
        self.inner_coil.off()
        delay(100.e-3)
        self.lightsheet.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

        self.outer_coil.discharge()

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