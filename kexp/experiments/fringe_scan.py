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

        # self.xvar('t_tof',np.linspace(100.,2000.,6)*1.e-6)
        # self.p.t_tof = 1000.e-6
        self.xvar('t_tof',[100*1.e-6]*500)

        # self.xvar('beans',[0]*1)

        self.p.frequency_tweezer_list = [71.3e6,80.e6]

        # ass = np.linspace(.18,.205,20)
        # a_lists = [[.78,ass1] for ass1 in ass]

        # ass = np.linspace(.74,.76,20)

        a_list = [.75,.25]
        # a_list = [.7,.2]
        self.p.amp_tweezer_list = a_list

        # self.xvar('pfrac_c_gmramp_end',np.linspace(.1,.5,8))
        # self.xvar('pfrac_r_gmramp_end',np.linspace(.1,.5,8))
        # self.p.pfrac_c_gmramp_end = 0.328
        # self.p.pfrac_r_gmramp_end = 0.271

        # self.xvar('t_lightsheet_rampup',np.linspace(.1,1.,8))
        # self.xvar('t_magtrap_ramp',np.linspace(.02,.5,8))
        # self.p.t_lightsheet_rampup = 
        # self.p.t_magtrap_ramp = 

        # self.xvar('i_evap1_current',np.linspace(190.,195.,8))
        # self.p.i_evap1_current = 193.
        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,20))
        self.p.t_lightsheet_rampdown = .381

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(4.,8.,20))
        self.p.v_pd_lightsheet_rampdown_end = 5.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.02,1.,6))
        self.p.t_tweezer_1064_ramp = .02
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-5.,-1.,6))
        self.p.v_tweezer_paint_amp_max = -4.

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.02,.55,8))
        self.p.t_tweezer_1064_rampdown2 = .3229

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.7,3.,8))
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.6

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.3,8))
        self.p.t_tweezer_1064_rampdown3 = .2
        
        # self.xvar('i_evap3_current',np.linspace(192.,194.,8))
        self.p.i_evap3_current = 193.

        self.p.t_tof = 150.e-6
        self.p.N_repeats = 1

        self.p.t_mot_load = 1.
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.

        # self.camera_params.amp_imaging = .11
        # self.xvar('amp_imaging',np.linspace(0.06,0.09,8))
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_evap3_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_evap1_current)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_evap1_current,
                             i_end=self.p.i_evap2_current)
        
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # # # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        # # # feshbach field ramp to field 3
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_evap3_current)
        
        # # # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        # # # tweezer evap 3 with constant trap frequency
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