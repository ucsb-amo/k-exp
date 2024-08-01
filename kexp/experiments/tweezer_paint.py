from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class tweezer_paint(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        # self.xvar('frequency_detuned_imaging',np.arange(400.,450.,3)*1.e6)
        self.p.frequency_detuned_imaging = 433.e6 # 150a0
        # self.p.frequency_detuned_imaging = 428.e6 # 150a0
        # self.p.frequency_detuned_imaging = 412.e6 # NI

        self.p.t_mot_load = .75

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(8.5,9.99,5))

        # self.xvar('v_pd_lightsheet_rampdown_end',np.linspace(3.,6.5,20))
        self.p.v_pd_lightsheet_rampdown_end = 5.358

        # self.xvar('freq_tweezer_modulation',np.linspace(100.e3,536.e3,20))
        # self.xvar('freq_tweezer_modulation',[])
        # self.xvar('v_tweezer_paint_amp_max',np.linspace(1.,6.,6))
        # self.p.freq_tweezer_modulation = 2.15e3
        self.p.v_tweezer_paint_amp_max = 4.

        # self.xvar('i_evap2_current',np.linspace(190.,195.,20))
        self.p.i_evap2_current = 193.7

        # self.xvar('v_pd_tweezer_1064_ramp_end', np.linspace(5.,9.9,6))
        self.p.v_pd_tweezer_1064_ramp_end = 7.9

        # self.xvar('t_tweezer_1064_ramp',np.linspace(10.,200.,6)*1.e-3)
        self.p.t_tweezer_1064_ramp = .09

        # self.xvar('v_pd_tweezer_1064_rampdown_end',np.linspace(.1,1.,8)) 
        self.p.v_pd_tweezer_1064_rampdown_end = .5

        # self.xvar('t_tweezer_1064_rampdown',np.linspace(0.01,.5,8))
        self.p.t_tweezer_1064_rampdown = .01

        # self.xvar('v_pd_tweezer_1064_rampdown2_end',np.linspace(.05,.09,10)) 
        self.p.v_pd_tweezer_1064_rampdown2_end = .06

        # self.xvar('t_tweezer_1064_rampdown2',np.linspace(0.01,.15,8))
        self.p.t_tweezer_1064_rampdown2 = .107

        # self.xvar('v_pd_tweezer_1064_rampdown3_end',np.linspace(.1,2.,20)) 
        self.p.v_pd_tweezer_1064_rampdown3_end = .5

        # self.xvar('t_tweezer_1064_rampdown3',np.linspace(0.1,.4,15))
        self.p.t_tweezer_1064_rampdown3 = .25
        
        # self.xvar('i_tweezer_evap_current',np.linspace(191.,194.5,8))
        self.p.i_tweezer_evap_current = 193.5
        # self.p.t_feshbach_field_ramp2 = .5

        # self.xvar('v_pd_tweezer_1064_adiabatic_stretch_ramp_end',np.linspace(self.p.v_pd_tweezer_1064_rampdown3_end,9.,10))
        self.p.v_pd_tweezer_1064_adiabatic_stretch_ramp_end = 5.
        self.p.t_tweezer_1064_adiabatic_stretch_ramp = .5

        # self.xvar('t_tweezer_hold',np.linspace(.05,1.,5))
        self.p.t_tweezer_hold = 100.e-3

        self.xvar('t_tof',np.linspace(10.,400.,5)*1.e-6)
        self.p.t_tof = 50.e-6
        self.p.N_repeats = [3]
        
        # self.xvar('dummy_z',[0]*5)

        self.p.n_tweezers = 1
        # self.xvar('frequency_tweezer_array_width',np.linspace(.2e6,1.e6,6))
        # self.p.frequency_tweezer_array_width = .7e6
        # self.p.amp_tweezer_auto_compute = False
        # self.xvar('amp_tweezer_list')
        self.p.amp_tweezer_list = [.17]

        # self.xvar('amp_imaging',np.linspace(.06,.19,15))
        # self.xvar('amp_imaging',np.linspace(.04,.09,20))
        self.camera_params.amp_imaging = 0.106
        self.camera_params.exposure_time = 10.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        self.camera_params.em_gain = 299

        self.finish_build(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(amp=self.p.amp_imaging)
        # self.set_high_field_imaging(i_outer = self.p.i_evap2_current)

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

        self.set_shims(v_zshim_current=self.p.v_zshim_current_magtrap,
                        v_yshim_current=self.p.v_yshim_current_magtrap,
                          v_xshim_current=self.p.v_xshim_current_magtrap)

        # magtrap start
        self.inner_coil.on()

        # ramp up lightsheet over magtrap
        
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

        for i in self.p.magtrap_ramp_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_ramp)

        delay(self.p.t_magtrap)

        for i in self.p.magtrap_rampdown_list:
            self.inner_coil.set_current(i_supply=i)
            delay(self.p.dt_magtrap_rampdown)

        self.inner_coil.off()
        
        self.outer_coil.on()
        delay(1.e-3)
        self.outer_coil.set_voltage()

        for i in self.p.feshbach_field_rampup_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_rampup)
        delay(20.e-3)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown,
                             v_list=self.p.v_pd_lightsheet_ramp_down_list)
        
        for i in self.p.feshbach_field_ramp_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp)
        delay(20.e-3)

        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_ramp,
                          paint=True,keep_trap_frequency_constant=False)

        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown2,
                             v_list=self.p.v_pd_lightsheet_ramp_down2_list)
        self.ttl.pd_scope_trig.pulse(t=1.e-6)
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown_list,
                          paint=True,keep_trap_frequency_constant=True)

        for i in self.p.feshbach_field_ramp2_list:
            self.outer_coil.set_current(i_supply=i)
            delay(self.p.dt_feshbach_field_ramp2)
        delay(30.e-3)
    
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown2,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown2_list,
                          paint=True,keep_trap_frequency_constant=True)

        
        self.tweezer.ramp(t=self.p.t_tweezer_1064_rampdown3,
                          v_ramp_list=self.p.v_pd_tweezer_1064_rampdown3_list,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        # self.tweezer.ramp(t=self.p.t_tweezer_1064_adiabatic_stretch_ramp,
        #                   v_ramp_list=self.p.v_pd_tweezer_1064_adiabatic_stretch_ramp_list,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        # self.outer_coil.set_current(i_supply=self.p.i_tweezer_evap_current)
        # delay(30.e-3)

        # self.ttl.pd_scope_trig.on()
        # self.outer_coil.off()
        # delay(self.p.t_feshbach_field_decay)
        # self.ttl.pd_scope_trig.off()

        self.lightsheet.off()
        self.tweezer.off()
    
        delay(self.p.t_tof)
        # self.flash_repump()
        self.abs_image()

        self.outer_coil.off()

        self.outer_coil.discharge()

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
