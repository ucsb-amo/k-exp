from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)
        
        # self.p.imaging_state = 1
        
        # self.xvar('t_tof',np.linspace(200.,3800.,10)*1.e-6)
        # self.xvar('dummy',[0]*3)
        # self.p.t_tof = 3500.e-6
        self.p.t_tof = 50.e-6
        # self.xvar('t_tof',[3800*1.e-6])

        # self.xvar('beans',[0]*1)

        self.p.frequency_tweezer_list = [72.2e6,74.e6,76.45e6,78.3e6]
        a_list = [.27,.1675,.1875,.365]
        # a_list = [.7,.2]
        self.p.amp_tweezer_list = a_list

        # self.xvar('pfrac_c_gmramp_end',np.linspace(0.1,5.,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,5.,8))
        
        # self.xvar('v_xshim_current_magtrap',np.linspace(0.,3.,8))
        # self.xvar('v_yshim_current_magtrap',np.linspace(5.,7.,8))

        # self.xvar('i_evap1_current',np.linspace(191.,194.,30))
        # self.p.i_evap1_current = 192.5

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,20))
        # self.p.t_lightsheet_rampdown = .4

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(5.,9.,10))
        # self.p.v_pd_lightsheet_rampdown_end = 3.
        # self.p.v_pd_lightsheet_rampdown_end = 7.2

        # self.xvar('i_evap2_current',np.linspace(192.5,194.5,20))
        # self.p.i_evap2_current = 198.02

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,1.,20))
        # self.p.t_tweezer_1064_ramp = .116

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.5,0.,15))
        self.p.v_tweezer_paint_amp_max = -3.5

        # self.xvar('t_lightsheet_rampdown2',np.linspace(.01,.5,20))
        # self.p.t_lightsheet_rampdown = .4

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.2,20))
        # self.p.t_tweezer_1064_rampdown = .02

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,2.5,15))
        # self.p.v_pd_tweezer_1064_rampdown_end = .45

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,10))
        # self.p.v_pd_tweezer_1064_rampdown2_end = .05

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.05,.5,8))
        # self.p.t_tweezer_1064_rampdown2 = .24

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.5,4.,15))
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        # self.p.t_tweezer_1064_rampdown3 = .13
        
        # self.xvar('i_evap3_current',np.linspace(196.5,198.,20))
        # self.p.i_evap3_current = 197.53

        self.p.N_repeats = 1

        self.p.t_mot_load = 1.

        # self.xvar('t_imaging_pulse',np.linspace(1.e-6,20.e-6,20))
        self.p.t_imaging_pulse = 10.e-6

        # self.xvar('amp_imaging',np.linspace(0.03,0.15,8))
        self.camera_params.amp_imaging = .09
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_high_field_imaging(i_outer=self.p.i_evap2_current)
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
        delay(1.e-3)
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
        
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # lightsheet ramp down (to off)
        # self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
        #                      v_start=self.p.v_pd_lightsheet_rampdown_end,
        #                      v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # # tweezer evap 1 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
        #                   v_start=self.p.v_pd_tweezer_1064_ramp_end,
        #                   v_end=self.p.v_pd_tweezer_1064_rampdown_end,
        #                   paint=True,keep_trap_frequency_constant=True)

        # # feshbach field ramp to field 3
        # self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
        #                      i_start=self.p.i_evap2_current,
        #                      i_end=self.p.i_evap3_current)
        
        # # # tweezer evap 2 with constant trap frequency
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
        
        self.lightsheet.off()
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()
        
        self.outer_coil.off()

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