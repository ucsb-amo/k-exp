from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from artiq.language.core import now_mu

class rf_scan(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=False)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])

        self.xvar('beans',[0,1]*300)

        # self.xvar('t_tof',np.linspace(50.,7000.,15)*1.e-6)
        # self.p.t_magtrap = 25.e-3
        # self.p.i_magtrap_init = 30.
        self.p.t_tweezer_1064_ramp = 150.e-3
        self.p.t_lightsheet_rampup = 200.e-3
        self.p.t_tweezer_hold = 40.e-3
        self.p.t_lightsheet_hold = 100.e-3

        # self.p.n_magtrap_ramp_steps = 4

        # self.p.v_pd_tweezer_1064_ramp_end = 4.5

        # self.p.frequency_tweezer_array_width = 0.
        # self.p.n_tweezers = 1

        self.p.t_tof = 2.e-6

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self): 
        self.dds.init_cooling()

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

        # self.ttl.pd_scope_trig.on()

        self.flash_cooler()

        self.dds.power_down_cooling()

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                          v_xshim_current=self.p.v_xshim_current_gm)
        
        self.ttl.pd_scope_trig.on()
        if self.p.beans == 0:
            self.inner_coil.igbt_ttl.on()
            # self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)

            self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,zero_integrator=True)

            for i in self.p.magtrap_ramp_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_ramp)
            delay(30.e-3)
            self.inner_coil.off()

            delay(self.p.t_tweezer_hold)
            self.tweezer.off()

        elif self.p.beans == 1:
            self.inner_coil.igbt_ttl.on()

            self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

            for i in self.p.magtrap_ramp_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_ramp)

            delay(self.p.t_magtrap)
            self.inner_coil.off()

            delay(self.p.t_lightsheet_hold)
            self.lightsheet.off()

        elif self.p.beans == 2:
            self.inner_coil.igbt_ttl.on()

            delay(self.p.t_lightsheet_rampup)

            for i in self.p.magtrap_ramp_list:
                self.inner_coil.set_current(i_supply=i)
                delay(self.p.dt_magtrap_ramp)
                
            delay(self.p.t_magtrap)
            self.inner_coil.off()
            
        elif self.p.beans == 3:
            pass

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