from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from artiq.language.core import now_mu

class evap(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='xy_basler',save_data=True)

        self.p.imaging_state = 2.
        # self.xvar('imaging_state',[2,1])

        # self.p.N_repeats = [3]

        # self.xvar('beans',[0,1]*300)

        self.p.v_pd_lightsheet_rampdown_end = 1.8
        # self.p.v_pd_lightsheet_rampdown_end = 1.25
        self.p.t_lightsheet_rampdown = 1.1*s

        self.p.v_pd_lightsheet_rampdown2_end = 0.18
        # self.p.v_pd_lightsheet_rampdown2_end = 0.
        self.p.t_lightsheet_rampdown2 = .7*s
        # self.p.t_lightsheet_rampdown2 = .01*s
        self.p.n_lightsheet_rampdown2_steps = 1000

        self.p.v_pd_tweezer_1064_rampdown_end = .41
        self.p.t_tweezer_1064_rampdown = .15*s

        self.p.i_evap1_current = 13.
        self.p.i_evap2_current = 13.5
        # self.p.i_evap3_current = 16.4

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(0.6,2.,6))

        # self.xvar('evap1_current',np.linspace(11.,14.,6))
        # self.xvar('evap2_current',np.linspace(9.,15.,10))

        # self.p.t_lightsheet_ramp_end = 100.e-3
        # self.xvar('t_lightsheet_rampup',np.linspace(10.e-3,self.p.t_lightsheet_ramp_end,10))
        # self.xvar('t_lightsheet_rampdown',np.linspace(1.,2.,6))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,.6,6))
        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(.15,.25,6))
        # self.xvar('t_lightsheet_rampdown2',np.linspace(.2,1.,6))

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,500.,6)*1.e-3)

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(.02,.7,6))
        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.38,.5,6))

        self.xvar('t_tof',np.linspace(5.,2000.,8)*1.e-6)

        # self.xvar('i_magtrap_ramp_start', np.linspace(40.,90.,10))
        # self.xvar('i_magtrap_init', np.linspace(20.,40.,10))

        self.p.t_lightsheet_hold = 500.e-3

        self.p.t_tweezer_1064_ramp = 250.e-3

        self.p.t_tweezer_hold = 30.e-3

        self.p.t_lightsheet_rampup = 200.e-3

        self.p.t_tof = 1800.e-6

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.finish_build(shuffle=False)

    @kernel
    def scan_kernel(self):

        # self.core.wait_until_mu(now_mu())
        # self.tweezer.set_static_tweezers(self.p.f_list,self.p.amp_list)
        # self.core.break_realtime()

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

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=self.p.v_yshim_current_gm,
                        v_xshim_current=self.p.v_xshim_current_gm)
        
        self.ttl.pd_scope_trig.on()
        self.inner_coil.igbt_ttl.on()
        self.inner_coil.set_current(i_supply=self.p.i_magtrap_ramp_start)
        # delay(self.p.t_magtrap)

        # ramp up lightsheet
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        # rampdown magtrap
        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        self.outer_coil.set_current(i_supply=self.p.i_evap1_current)
        self.outer_coil.set_voltage(v_supply=9.)
        delay(20.e-3)
        self.inner_coil.off()

        self.outer_coil.on(i_supply=self.p.i_evap1_current)

        delay(30.e-3)
        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown)

        self.outer_coil.set_current(i_supply=self.p.i_evap2_current)
        # delay(20.e-3)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
        
        self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)
        # delay(self.p.t_tweezer_hold)
        self.outer_coil.off()
        self.ttl.pd_scope_trig.off()
        delay(1.5e-3)

        self.lightsheet.off()

        # self.tweezer.off()
    
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