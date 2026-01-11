from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        
        # self.p.t_tof = 4250.e-6
        self.p.t_tof = 400.e-6
        # self.xvar('t_tof',np.linspace(100.,3000.,20)*1.e-6) 
        # self.xvar('dumy',[0.]*3)
    
        # self.xvar('hf_imaging_detuning', [-617.e6,-505.e6]*1)

        # self.p.t_magtrap = .5

        # self.xvar('t_feshbach_field_rampup',np.linspace(.02,.3,8))
        # self.p.t_feshbach_field_rampup = 100.e-3

        # self.xvar('t_magtrap_rampdown',np.linspace(15.,200.,8)*1.e-3)
        # self.p.t_magtrap_rampdown = 41.e-3

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(186.,194.,8))
        # self.p.i_hf_lightsheet_evap1_current = 195.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.3,1.,8))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .55

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,1500.,20)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = .45

        # self.xvar('t_hf_lightsheet_rampdown2',np.linspace(10.,60.,15)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown2 = .02

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.5,194.,8))
        # self.p.i_hf_tweezer_load_current = 193.1

        # self.p.i_image_current = 190.
 
        # self.xvar('v_pd_hf_tweezer_1064_ramp_end',np.linspace(3.,9.5,10))
        # self.p.v_pd_hf_tweezer_1064_ramp_end = 8.8

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-4.,.5,8))
        # self.p.v_hf_tweezer_paint_amp_max = -1.5
# 
        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(.02,1.,15))
        # self.p.t_hf_tweezer_1064_ramp = .7

        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.5,194.5,8))
        # self.p.i_hf_tweezer_evap1_current = 193.47

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(.5,2.,10))
        # self.p.v_pd_hf_tweezer_1064_rampdown_end = 1.5
# 
        # self.xvar('t_hf_tweezer_1064_rampdown',np.linspace(50.,300.,8)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown = 121.e-3        

        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(192.5,195.,8))
        # self.p.i_hf_tweezer_evap2_current = 194.1

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.1,.165,10))
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = .143

        # self.xvar('t_hf_tweezer_1064_rampdown2',np.linspace(100.,800.,8)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown2 = 500.e-3

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(3.5,7.,10))
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 3.5

        # self.xvar('t_hf_tweezer_1064_rampdown3',np.linspace(100.,800.,8)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown3 = 300.e-3

        # self.xvar('i_tunnel',np.linspace(180.,190.,20)) 
        self.p.i_tunnel = 182. 

        self.p.i_hf_raman = 191. 

        # self.xvar('t_tweezer_hold',np.linspace(0.,300.,10)*1.e-3)
        self.p.t_tweezer_hold = 10.0e-3

        # self.xvar('fringe_repeats',np.linspace(1.,300.,300))

        # self.p.frequency_tweezer_list = [75.8e6]

        # self.p.frequency_tweezer_list = [75.8e6]
        # self.p.frequency_tweezer_list = [75.8e6, 76.5e6]
        # self.p.frequency_tweezer_list = [72.5e6]

        # a_list = [.18]
        # a_list = [.18,.19]
        # a_list = [.5]
        # self.p.amp_tweezer_list = a_list

        # self.xvar('amp_tweezer',np.linspace(.1,.3,20))

        # self.xvar('hf_imaging_detuning', np.arange(-580.,-540.,3.)*1.e6)
        # self.p.hf_imaging_detuning = -604.e6
        # self.p.hf_imaging_detuning = -609.e6 # 192.
        self.p.hf_imaging_detuning = -617.5e6 # 193.2
        # self.p.hf_imaging_detuning = -562.e6 # 182.

        # self.xvar('t_imaging_pulse',np.linspace(10.,500.,10)*1.e-6)
        # self.p.t_imaging_pulse = 20.e-6    
        
        # self.camera_params.exposure_time = 15.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time

        # self.camera_params.em_gain = 1.

        # self.xvar('img_power', np.linspace(.05,2.,15))
        self.p.amp_imaging = .2
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_raman)
        self.imaging.set_power(self.p.amp_imaging)

        # self.tweezer.traps[0].set_amp(self.p.amp_tweezer)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
        self.set_shims(0.,0.,0.)
        
        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                             v_start=self.p.v_pd_lightsheet_rampup_end,
                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_lightsheet_evap1_current,
                             i_end=self.p.i_hf_tweezer_load_current)

        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                        v_start=0.,
                        v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                        paint=True,keep_trap_frequency_constant=False)
        self.ttl.pd_scope_trig.pulse(1.e-6)
        # delay(500.e-3)

        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_evap1_current,
                             i_end=self.p.i_hf_tweezer_evap2_current)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)

        # tweezer evap 3 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
                          v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
                          paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        self.outer_coil.ramp_supply(t=10.e-3,
                             i_start=self.p.i_hf_tweezer_evap2_current,
                             i_end=self.p.i_hf_raman)
        
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.tweezer.off()

        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)