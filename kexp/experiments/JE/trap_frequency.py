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
        
        # self.xvar('frequency_detuned_imaging',np.arange(240.,550.,6)*1.e6)
        
        # self.xvar('t_tof',np.linspace(800.,3500.,10)*1.e-6)
        self.p.t_tof = 500.e-6
        # self.xvar('t_tof',[500*1.e-6]*3)

        # self.xvar('t_tweezer_mod',np.linspace(3.,50.,20)*1.e-3)
        self.p.t_tweezer_mod = 300.e-3

        self.xvar('f_tweezer_mod',np.linspace(30.,100.,70))
        self.p.f_tweezer_mod = 64.

        self.p.x_tweezer_mod_amp = 1.e-6

        # self.xvar('t_tunnel',np.linspace(.0,200.,80)*1.e-3)
        # self.xvar('t_tunnel',[20*1.e-3]*3)
        self.p.t_tunnel = 1.e-3

        # self.p.frequency_tweezer_list = [73.7e6,77.3e6]
        self.p.frequency_tweezer_list = [73.15e6,77.e6]

        # ass = np.linspace(.42,.46,20)
        # a_lists = [[ass1,.51] for ass1 in ass]

        # self.xvar('amp_tweezer_list',a_lists)

        a_list = [.0,.5]
        # a_list = [.2,.23]
        self.p.amp_tweezer_list = a_list

        self.p.t_amp_ramp = 1.e-3
        self.p.amp_final = .786

        # self.xvar('pfrac_d1_c_gm',np.linspace(.6,.99,8))
        # self.xvar('v_yshim_current_gm',np.linspace(.5,5.,20))

        # self.xvar('pfrac_d1_c_gm',np.linspace(.6,.99,8))
        # self.xvar('pfrac_d1_r_gm',np.linspace(.6,.99,8))

        # self.xvar('detune_d1_c_gm',np.linspace(1.,10.,8))
        # self.xvar('detune_d1_r_gm',np.linspace(1.,10.,8))

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.1,.5,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.5,8))
        self.p.pfrac_c_gmramp_end = .271
        self.p.pfrac_r_gmramp_end = .15

        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,1.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(3.,7.,8))

        # self.xvar('i_evap1_current',np.linspace(194.,198.,20))
        # self.p.i_evap1_current = 192.

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(4.,8.,10))
        self.p.v_pd_lightsheet_rampdown_end = 7.
        # self.p.v_pd_lightsheet_rampdown_end = 7.1

        # self.xvar('i_evap2_current',np.linspace(196.5,199.,10))
        self.p.i_evap2_current = 198.2

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.9,8))
        self.p.t_tweezer_1064_ramp = .38

        # self.xvar('v_pd_tweezer_1064_ramp_end',np.linspace(4.,9.9,20))
        self.p.v_pd_tweezer_1064_ramp_end = 9.

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-4.,4.,20))
        self.p.v_tweezer_paint_amp_max = -2.3

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.3,8))
        self.p.t_tweezer_1064_rampdown = .05

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,8))
        self.p.v_pd_tweezer_1064_rampdown2_end = .07

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.4,8))
        self.p.t_tweezer_1064_rampdown2 = .15
 
        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.15,.5,10))
        self.p.v_pd_tweezer_1064_rampdown3_end = .4
        # self.p.v_pd_tweezer_1064_rampdown3_end = .35

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .18
        
        # self.xvar('i_evap3_current',np.linspace(196.5,199.,10))
        # self.p.i_evap3_current = 197.8
        self.p.i_evap3_current = 198.5

        # self.xvar('i_tunnel_current',np.linspace(184.,197.,20))
        self.p.i_tunnel_current = 196.8
        self.p.t_tunnel_current = 10.e-3

        # self.xvar('i_non_inter_current',np.linspace(181.3,190.,8))
        # self.xvar('t_non_inter',np.linspace(3.e-3,20.e-3,6))

        self.p.i_non_inter_current = 181.3
        # self.p.i_non_inter_current = 197.
        self.p.t_non_inter = 10.e-3

        # self.p.t_tof = 800.e-6
        # self.p.N_repeats = 300
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.

        self.camera_params.amp_imaging = .08
        # self.xvar('amp_imaging',np.linspace(0.1,0.18,8))
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        

        # self.tweezer.traps[0].linear_amplitude_ramp(1.e-3,.47,False)

        # self.tweezer.set_amp(0,.49)

        self.tweezer.traps[1].sine_move(t_mod=self.p.t_tweezer_mod,x_mod=self.p.x_tweezer_mod_amp,f_mod=self.p.f_tweezer_mod,trigger=False)
        delay(100.e-3)
        
        # self.set_high_field_imaging(i_outer=self.p.i_non_inter_current)
        self.set_high_field_imaging(i_outer=self.p.i_evap3_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        # self.set_imaging_detuning(self.p.frequency_detuned_imaging)

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
        
        # # tweezer evap 1 with constant trap frequency
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
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.outer_coil.ramp_pid(t=self.p.t_non_inter,
        #                       i_start=self.p.i_evap3_current,
        #                       i_end=self.p.i_non_inter_current)
        
        # delay(10.e-3)

        # self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_paint_rampdown,)
        
        # delay(.5)
        # self.tweezer.trigger()
        # delay(1.e-3)

        delay(self.p.t_tunnel)

        self.tweezer.trigger()
        delay(self.p.t_tweezer_mod)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        self.outer_coil.stop_pid()
        delay(10.e-3)
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