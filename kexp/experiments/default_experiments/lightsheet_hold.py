from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class lightsheet_hold(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select="xy_basler",save_data=True)

        self.xvar('t_lightsheet_hold',np.linspace(1.,100.,2)*1.e-3)
        self.p.t_lightsheet_hold = 40.e-3

        self.p.t_tof = 10.e-6
        self.p.t_mot_load = .75
        self.camera_params.amp_imaging = .5
        self.p.N_repeats = 1

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_init)

        self.set_shims(v_zshim_current=self.p.v_zshim_current_gm,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        # self.release()
        self.switch_d2_3d(0)
        self.switch_d1_3d(0)

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.inner_coil.on()

        # # ramp up lightsheet over magtrap
        self.lightsheet.ramp(self.p.t_lightsheet_rampup,
                             self.p.v_pd_lightsheet_rampup_start,
                             self.p.v_pd_lightsheet_rampup_end)

        self.ttl.pd_scope_trig.pulse(1.e-6)
        # mag trap ramp up
        self.inner_coil.ramp(t=self.p.t_magtrap_ramp,
                             i_start=self.p.i_magtrap_init,
                             i_end=self.p.i_magtrap_ramp_end)
        
        # magtrap + lightsheet hold
        delay(self.p.t_magtrap)

        # mag trap ramp down
        self.inner_coil.ramp(t=self.p.t_magtrap_rampdown,
                             i_start=self.p.i_magtrap_ramp_end,
                             i_end=0.)
        self.inner_coil.off()
        delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()
        self.ttl.pd_scope_trig.off()

        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()
       
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