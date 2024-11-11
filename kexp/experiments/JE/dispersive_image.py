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
        
        # self.xvar('t_tof',np.linspace(600.,2500.,15)*1.e-6)
        # self.xvar('dummy',[0]*3)
        self.p.t_tof = 100.e-6
        # self.p.t_tof = 2200.e-6
        # self.xvar('t_tof',[500*1.e-6]*4)

        # self.xvar('beans',[0]*1)

        self.p.frequency_tweezer_list = [73.7e6,77.3e6]

        a_list = [.43,.54]
        # a_list = [.7,.2]
        self.p.amp_tweezer_list = a_list

        self.pfrac_c_gmramp_end = 0.38
        self.pfrac_r_gmramp_end = 0.27

        # self.xvar('i_evap1_current',np.linspace(190.,195.,20))
        # self.p.i_evap1_current = 192.

        # self.xvar('t_lightsheet_rampdown',np.linspace(.02,1.,8))
        # self.p.t_lightsheet_rampdown = .16

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,8.,10))
        # self.p.v_pd_lightsheet_rampdown_end = 3.
        self.p.v_pd_lightsheet_rampdown_end = 5.5

        # self.xvar('i_evap2_current',np.linspace(192.5,194.5,8))
        self.p.i_evap2_current = 193.8

        # self.xvar('t_tweezer_1064_ramp',np.linspace(.012,.3,20))
        # self.p.t_tweezer_1064_ramp = .17

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-5.,0.,10))
        self.p.v_tweezer_paint_amp_max = 1.8

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.012,.1,8))
        # self.p.t_tweezer_1064_rampdown = .12

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(0.1,1.5,8))
        self.p.v_pd_tweezer_1064_rampdown_end = .7

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(0.04,.099,5))
        self.p.v_pd_tweezer_1064_rampdown2_end = .06

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.1,.8,8))
        self.p.t_tweezer_1064_rampdown2 = .4

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.4,2.,8))
        self.p.v_pd_tweezer_1064_rampdown3_end = 1.4

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.02,.5,8))
        self.p.t_tweezer_1064_rampdown3 = .1
        
        # self.xvar('i_evap3_current',np.linspace(192.5,194.3,8))
        self.p.i_evap3_current = 193.6

        self.p.N_repeats = 1

        self.p.t_mot_load = 1.

        # self.xvar('t_imaging_pulse',np.linspace(1.e-6,20.e-6,20))
        self.p.t_imaging_pulse = 10.e-6

        self.xvar('detuning_dispersive_imaging',np.arange(-800.e6,-615.e6,6.e6))
        # self.xvar('detuning_dispersive_imaging',np.arange(-625.e6,-610.e6,1.e6))
        # self.p.detuning_dispersive_imaging = -736.e6

        self.camera_params.amp_imaging = .12
        # self.xvar('amp_imaging',np.linspace(0.1,0.18,8))
        self.camera_params.exposure_time = 10.e-6
        self.p.t_imaging_pulse = self.camera_params.exposure_time

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.detuning_dispersive_imaging)
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
        
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_start=self.p.v_pd_lightsheet_rampdown_end,
                             v_end=self.p.v_pd_lightsheet_rampdown2_end)
        
        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)

        # feshbach field ramp to field 3
        self.outer_coil.ramp(t=self.p.t_feshbach_field_ramp2,
                             i_start=self.p.i_evap2_current,
                             i_end=self.p.i_evap3_current)
        
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
        
        self.lightsheet.off()

        self.dispersive_image(repeats=3)

        self.tweezer.off()

        # delay(self.p.t_tof)
        # self.abs_image()
        
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