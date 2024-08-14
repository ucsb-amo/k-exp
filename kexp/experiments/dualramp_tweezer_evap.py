from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

from artiq.language.core import now_mu

class tweezer_evap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.imaging_state = 2.

        # self.p.N_repeats = [3]

        # self.xvar('beans',[0,1]*300)

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(0.95,2.,6))

        # self.xvar('evap1_current',np.linspace(11.5,15.3,6))
        # self.xvar('evap2_current',np.linspace(11.5,20.,10))
        # self.xvar('evap3_current',np.linspace(11.,15.,6))

        # self.xvar('t_lightsheet_rampup',np.linspace(10.e-3,self.p.t_lightsheet_ramp_end,10))
        # self.xvar('t_lightsheet_rampdown',np.linspace(.5,2.,6))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(1.,.6,6))
        # self.xvar('v_pd_lightsheet_rampdown2_end',np.linspace(.13,.2,6))
        # self.xvar('t_lightsheet_rampdown2',np.linspace(0.1,1.,6))

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,600.,6)*1.e-3)
        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(.15,.4,6))

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(.01,.12,10))
        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.085,.095,6))

        # self.xvar('tweezer_1064_max_freq',np.linspace(1.,3.,10)*1.e6)

        # self.xvar('pfrac_c_gmramp_end', np.linspace(.1,.4,6))
        # self.xvar('pfrac_c_gmramp_end', np.linspace(.1,.4,6))

        # self.xvar('t_tweezer_hold',np.linspace(50.,1000.,3)*1.e-3)
        self.p.t_tweezer_hold = 50.e-3
        
        # self.xvar('t_tof',np.linspace(1.,32.,10)*1.e-6)  
        # self.xvar('t_tof',np.linspace(1.,15.,10)*1.e-6)   
        self.xvar('t_tof',np.linspace(5.,250.,10)*1.e-6)     

        # self.p.v_pd_lightsheet_rampdown2_end = .2

        self.p.v_pd_lightsheet_rampdown2_end = 0.
        self.p.t_lightsheet_rampdown2 = 0.05
        
        # self.p.i_evap1_current = 12.4
        # self.p.i_evap2_current = 12.
        # self.p.i_evap2_current = 12.3
        # self.p.i_evap3_current = 12.6
        self.p.i_evap2_current = 13.8
        # self.p.i_evap2_current = 35.
        # self.xvar('i_evap2_current',np.linspace(12.,45.,8))

        self.p.t_tweezer_1064_ramp = 150.e-3
        # self.p.t_tweezer_1064_ramp = 5.e-3
        # self.p.v_pd_tweezer_1064_ramp_end = 0.35
        self.p.v_pd_tweezer_1064_ramp_end = 1.
        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(0.05,4.5,10))

        self.p.t_tweezer_1064_rampdown = .15*s
        self.p.v_pd_tweezer_1064_rampdown_end = .093

        self.p.tweezer_1064_max_freq = 1.e6

        # self.p.t_tweezer_hold = 100.e-3

        self.p.t_lightsheet_rampup = 200.e-3

        # self.p.t_tof = 70.e-6
        self.p.t_tof = 10.*1.e-6

        self.camera_params.amp_imaging = .07
        self.camera_params.exposure_time = 15.e-6

        self.p.t_mot_load = 0.5
        self.p.t_bias_off_wait = 2.e-3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.dds.init_cooling()

        self.core.wait_until_mu(now_mu())
        self.tweezer.set_static_tweezers(self.p.f_list,self.p.amp_list)
        self.core.break_realtime()

        self.dds.ry_405.on()
        self.dds.ry_980.on()

        self.tweezer.awg_trg_ttl.pulse(t=1.e-6)

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
        
        # self.lightsheet.ramp_down2(t=self.p.t_lightsheet_rampdown2)

        # self.outer_coil.set_current(i_supply=self.p.i_evap3_current)
        # delay(20.e-3)

        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp)
 
        self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampdown2, v_ramp_list=self.p.v_pd_lightsheet_ramp_down2_list)
        self.lightsheet.off()
        delay(self.p.t_tweezer_hold)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list)
        
        self.outer_coil.off()
        self.ttl.pd_scope_trig.off()
        delay(1.5e-3)

        self.tweezer.off()
    
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