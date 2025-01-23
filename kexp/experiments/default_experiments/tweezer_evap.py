from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)
        
        # self.xvar('frequency_detuned_imaging',np.arange(-680.,-600.,10)*1.e6)

        self.p.frequency_tweezer_list = [73.2e6,77.e6]

        self.p.amp_tweezer_list = [.43,.51]

        self.p.t_tof = 50.e-6
        # self.xvar('t_tof',np.linspace(200.,2000.,10)*1.e-6)
        # self.xvar('t_tof',[800*1.e-6]*3)``

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.1,.6,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.7,8))

        # self.xvar('i_magtrap_init',np.linspace(20.,95,8))
        self.p.i_magtrap_init = 73.

        # self.xvar('v_zshim_current_magtrap_init',np.linspace(.0,3.,10))
        self.p.v_zshim_current_magtrap_init = .7

        # self.xvar('v_zshim_current_magtrap',np.linspace(.0,.7,20))
        self.p.v_zshim_current_magtrap = .0

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,1.,10))
        # self.p.v_xshim_current_magtrap = .14

        # self.xvar('v_yshim_current_magtrap',np.linspace(2.,9.,10))
        # self.p.v_yshim_current_gm = 2.545

        # self.xvar('i_magtrap_init',np.linspace(20.,70.,8))

        # self.xvar('i_magtrap_ramp_end',np.linspace(30.,95.,8))
        self.p.i_magtrap_ramp_end = 48.

        # self.xvar('t_magtrap_ramp',np.linspace(.05,6.5,8))
        self.p.t_magtrap_ramp = 2.8

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,9.,10))
        self.p.v_pd_lightsheet_rampdown_end = 6.

        self.xvar('v_tweezer_paint_amp_max',np.linspace(-4.,4.,5))
        self.p.v_tweezer_paint_amp_max = -1.79

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.9,8))
        # self.p.t_tweezer_1064_ramp = .38

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(4.,9.9,20))
        # self.p.v_pd_tweezer_1064_ramp_end = 9.

        # self.xvar('i_evap2_current',np.linspace(196.5,200.,20))
        # self.p.i_evap2_current = 198.2

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.3,8))
        # self.p.t_tweezer_1064_rampdown = .05

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        # self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('i_evap3_current',np.linspace(196.5,200.,20))
        self.p.i_evap3_current = 199.3

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,8))
        # self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.4,8))
        # self.p.t_tweezer_1064_rampdown2 = .15
 
        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.25,1.,10))
        self.p.v_pd_tweezer_1064_rampdown3_end = .4
        # self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        # self.p.t_tweezer_1064_rampdown3 = .18
        
        

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.
        
        # self.xvar('amp_imaging',np.linspace(.1,.4,5))
        self.p.amp_imaging = .1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_evap2_current)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # # lightsheet ramp down (to off)
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()

        # # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # # feshbach field ramp to field 3
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # self.outer_coil.start_pid()
        
        # # tweezer evap 2 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
        #                   v_start=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
        #                   paint=True,keep_trap_frequency_constant=True)
        
        # # tweezer evap 3 with constant trap frequency
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.outer_coil.stop_pid()
        # delay(10.e-3)

        self.outer_coil.off()

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