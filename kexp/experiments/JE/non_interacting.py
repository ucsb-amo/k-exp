from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_snug(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)
        
        self.xvar('frequency_detuned_imaging',np.arange(-580.,-500.,3)*1.e6)
        
        # self.xvar('t_tof',np.linspace(200.,4000.,10)*1.e-6)
        self.p.t_tof = 10.e-6
        # self.xvar('t_tof',[100*1.e-6]*3)

        # self.xvar('x_move',np.linspace(-3.5,-2.75,20)*1.e-6)
        self.p.x_move = 3.e-6
        # self.xvar('t_tweezer_single_move',np.linspace(3.,50.,20)*1.e-3)
        self.p.t_tweezer_single_move = 10.e-3

        # self.xvar('t_tunnel',np.linspace(1.,5000.,8)*1.e-6)
        # self.xvar('t_tunnel',[20*1.e-3]*3)
        self.p.t_tunnel = 10.e-6

        # self.p.frequency_tweezer_list = [73.7e6,77.3e6]
        self.p.frequency_tweezer_list = [73.48e6,77.e6]

        # ass = np.linspace(.42,.46,20)
        # a_lists = [[ass1,.51] for ass1 in ass]

        # self.xvar('amp_tweezer_list',a_lists)

        a_list = [.46,.45]
        # a_list = [.2,.23]
        self.p.amp_tweezer_list = a_list

        self.p.t_amp_ramp = 1.e-3
        self.p.amp_final = .786

        # self.xvar('i_evap1_current',np.linspace(190.,195.,20))
        # self.p.i_evap1_current = 192.

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,8.,20))
        # self.p.v_pd_lightsheet_rampdown_end = 3.
        # self.p.v_pd_lightsheet_rampdown_end = 7.1

        # self.xvar('i_evap2_current',np.linspace(194.5,199.,10))
        # self.p.i_evap2_current = 197.5

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.3,8))
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(2.,9.9,20))
        # self.p.v_pd_tweezer_1064_ramp_end = 6.5

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.5,-1.,20))
        self.p.v_tweezer_paint_amp_max = -2.4

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.1,10))
        # self.p.t_tweezer_1064_rampdown = .04

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        # self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,5))
        # self.p.v_pd_tweezer_1064_rampdown2_end = .06

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.6,8))
        # self.p.t_tweezer_1064_rampdown2 = .15

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.1,.5,20))
        # self.p.v_pd_tweezer_1064_rampdown3_end = .9
        self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .06
        
        # self.xvar('i_evap3_current',np.linspace(196.5,199.,20))
        # self.p.i_evap3_current = 197.8
        self.p.i_evap3_current = 197.4

        # self.xvar('i_non_inter_current',np.linspace(181.,183.,8))
        self.p.i_non_inter_current = 181.3
        self.p.t_non_inter = 50.e-3

        # self.xvar('v_pd_ramp_back_up',np.linspace(3.6,4.05,10))
        self.p.t_tweezer_ramp_back_up = 100.e-3
        # self.p.v_pd_ramp_back_up = 3.9
        self.p.v_pd_ramp_back_up = .36

        # self.p.t_tof = 800.e-6
        # self.p.N_repeats = 300
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.

        self.camera_params.amp_imaging = .08
        # self.xvar('amp_imaging',np.linspace(0.1,0.18,8))
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.tweezer.traps[0].cubic_move(t_move=self.p.t_tweezer_single_move,
        #                                  x_move=self.p.x_move,trigger=False)
        
        # self.set_high_field_imaging(i_outer=self.p.i_non_inter_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        self.set_imaging_detuning(self.p.frequency_detuned_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.on()
        # delay(1.e-3)
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
        
        # lightsheet ramp down (to off)
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
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        self.outer_coil.ramp_pid(t=self.p.t_non_inter,
                             i_start=self.p.i_evap3_current,
                             i_end=self.p.i_non_inter_current)

        delay(75.e-3)   
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_ramp_back_up,
                          v_start=self.p.v_pd_tweezer_1064_rampdown3_end,
                          v_end=self.p.v_pd_ramp_back_up,
                          paint=True,keep_trap_frequency_constant=False,low_power=True,v_awg_am_max=self.tweezer.paint_amp_dac.v)  
        
        # delay(self.p.t_tweezer_ramp_back_up)

        delay(self.p.t_tunnel)

        

        delay(self.p.t_tof)
        self.abs_image()

        self.tweezer.off()

        self.outer_coil.stop_pid()
        delay(50.e-3)
        self.outer_coil.off()
        # self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)