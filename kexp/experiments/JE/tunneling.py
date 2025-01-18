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

        self.p.frequency_tweezer_list = [73.2e6,76.8e6]

        self.p.x_move = 1.5e-6
        self.p.t_tweezer_single_move = 10.e-3

        self.p.amp_tweezer_list = [.43,0.]

        self.p.t_tunnel = .5

        self.p.t_tof = 200.e-6
        # self.xvar('t_tof',np.linspace(1000.,3500.,10)*1.e-6)
        # self.xvar('t_tof',[100*1.e-6]*3)

        # self.xvar('t_amp_ramp',np.linspace(5.e-3,1500.e-3,20))
        self.p.t_amp_ramp = 800.e-3

        self.xvar('amp_initial',np.linspace(.39,.56,10))
        self.p.amp_initial = .4

        # self.xvar('amp_final',np.linspace(.49,.57,10))
        self.p.amp_final = .57

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.1,.6,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.7,8))

        # self.xvar('i_magtrap_init',np.linspace(20.,95,8))
        # self.p.i_magtrap_init = 73.

        # self.xvar('v_zshim_current_magtrap_init',np.linspace(.0,3.,10))
        # self.p.v_zshim_current_magtrap_init = .7

        # self.xvar('v_zshim_current_magtrap',np.linspace(.0,.7,20))
        # self.p.v_zshim_current_magtrap = .0

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,1.,10))
        # self.p.v_xshim_current_magtrap = .14

        # self.xvar('v_yshim_current_magtrap',np.linspace(2.,9.,10))
        # self.p.v_yshim_current_gm = 2.545

        # self.xvar('i_magtrap_init',np.linspace(20.,70.,8))

        # self.xvar('i_magtrap_ramp_end',np.linspace(30.,95.,8))
        # self.p.i_magtrap_ramp_end = 48.

        # self.xvar('t_magtrap_ramp',np.linspace(.05,6.5,8))
        # self.p.t_magtrap_ramp = 2.8

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(4.,9.,10))
        # self.p.v_pd_lightsheet_rampdown_end = 5.8

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-4.,4.,20))
        # self.p.v_tweezer_paint_amp_max = -2.3

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.9,8))
        # self.p.t_tweezer_1064_ramp = .38

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(4.,9.9,20))
        # self.p.v_pd_tweezer_1064_ramp_end = 9.

        # self.xvar('i_evap2_current',np.linspace(197.5,200.,10))
        # self.p.i_evap2_current = 198.2

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.3,8))
        # self.p.t_tweezer_1064_rampdown = .053

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        # self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('i_evap3_current',np.linspace(197.5,200.,10))
        # self.p.i_evap3_current = 199.3

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,8))
        # self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.4,8))
        # self.p.t_tweezer_1064_rampdown2 = .15
 
        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.4,1.5,20))
        # self.p.v_pd_tweezer_1064_rampdown3_end = .73
        # self.p.v_pd_tweezer_1064_rampdown3_end = 1.

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        # self.p.t_tweezer_1064_rampdown3 = .18

        self.p.i_non_inter_current = 181.3
        self.p.t_non_inter = 50.e-3      

        self.p.N_repeats = 3
        self.p.t_mot_load = 1.
        
        # self.xvar('amp_imaging',np.linspace(.1,.4,5))
        # self.p.amp_imaging = .1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.tweezer.traps[1].set_amp(self.p.amp_initial,trigger=False)

        delay(50.e-3)

        # self.tweezer.traps[1].linear_amplitude_ramp(t_ramp=self.p.t_amp_ramp,
        #                                             amp_f=self.p.amp_final,
        #                                             trigger=False)

        # delay(500.e-3)

        self.tweezer.traps[0].cubic_move(t_move=self.p.t_tweezer_single_move,
                                         x_move=-self.p.x_move,trigger=False)
        
        delay(100.e-3)

        self.tweezer.traps[1].cubic_move(t_move=self.p.t_tweezer_single_move,
                                         x_move=self.p.x_move,trigger=False)
        
        delay(100.e-3)

        self.set_high_field_imaging(i_outer=self.p.i_non_inter_current)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        

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
        
        # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        self.lightsheet.off()

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_evap3_current)
        
        self.outer_coil.start_pid()
        
        # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # tweezer evap 3 with constant trap frequency
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        self.outer_coil.ramp_pid(t=self.p.t_non_inter,
                             i_start=self.p.i_evap3_current,
                             i_end=self.p.i_non_inter_current)
        
        self.tweezer.trigger()
        delay(.001)

        # self.tweezer.trigger()
        delay(self.p.t_amp_ramp)

        delay(1.e-3)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_single_move)

        delay(1.e-3)

        # delay(.5)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_single_move)

        # delay(.5)
        
        # delay(self.p.t_tunnel)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()
        delay(10.e-3)

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