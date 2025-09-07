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
        
        self.p.t_tof =3500.e-6
        # self.p.t_tof = 1000.e-6
        # self.xvar('t_tof',np.linspace(2000.,4500.,20)*1.e-6) 
        # self.xvar('dumy',[0]*10)
    
        # self.xvar('hf_imaging_detuning', [-617.e6,-505.e6]*1)

        # self.xvar('beans',[0]*10)
        
        self.p.t_lightsheet_hold = .1

        # self.p.t_magtrap = .5

        # self.xvar('t_feshbach_field_rampup',np.linspace(.02,.3,8))
        # self.p.t_feshbach_field_rampup = 100.e-3

        # self.xvar('t_magtrap_rampdown',np.linspace(15.,200.,8)*1.e-3)
        # self.p.t_magtrap_rampdown = 41.e-3

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(186.,194.,8))
        # self.p.i_hf_lightsheet_evap1_current = 191.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.3,1.5,15))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .65

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,1500.,20)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = .64

        # self.xvar('t_hf_lightsheet_rampdown2',np.linspace(10.,60.,15)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown2 = .02

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.,194.5,15))
        # self.p.i_hf_tweezer_load_current = 192.5

        # self.p.i_image_current = 190.
 
        # self.xvar('v_pd_hf_tweezer_1064_ramp_end',np.linspace(5.,9.3,15))
        # self.p.v_pd_hf_tweezer_1064_ramp_end = 6.5

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-2.,2.,12))
        # self.p.v_hf_tweezer_paint_amp_max = 1.
        self.p.v_hf_tweezer_paint_amp_max = .545

        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(.05,.6,8))
        # self.p.t_hf_tweezer_1064_ramp = .285

        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.5,194.5,20))
        self.p.i_hf_tweezer_evap1_current = 193.9

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(.2,1.5,8))
        # self.p.v_pd_hf_tweezer_1064_rampdown_end = 1.13

        # self.xvar('t_hf_tweezer_1064_rampdown',np.linspace(50.,400.,20)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown = 200.e-3        

        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(192.5,194.5,20))
        self.p.i_hf_tweezer_evap2_current = 193.4

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.07,.18,12))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .12

        # self.xvar('t_hf_tweezer_1064_rampdown2',np.linspace(100.,1200.,15)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown2 = 700.e-3  

        # self.xvar('i_hf_tweezer_evap3_current',np.linspace(193.,194.5,8))
        # self.p.i_hf_tweezer_evap3_current = 193.7 

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end', np.linspace(.1,.2,8))
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = .1

        # self.xvar('t_hf_tweezer_1064_rampdown3',np.linspace(100.,800.,8)*1.e-3) 
        # self.p.t_hf_tweezer_1064_rampdown3 = 300.e-3   

        # self.xvar('i_tunnel',np.linspace(180.,194.,20)) 
        self.p.i_tunnel = 182. 

        # self.xvar('t_tweezer_hold',np.linspace(0.,80.,20)*1.e-3)
        self.p.t_tweezer_hold = 1.e-3

        # self.xvar('fringe_repeats',np.linspace(1.,300.,300))

        # self.xvar('ce_frequency',np.linspace(73.6e6,73.8e6,15))

        self.p.frequency_tweezer_list = [73.71e6, 75.4e6]
        # self.p.frequency_tweezer_list = [76.e6, 76.5e6]
        # self.p.frequency_tweezer_list = [72.5e6]

        # a_list = [.164,.15]
        a_list = [.1607,.15]
        # a_list = [self.p.amp_tweezer_final,.15]
        # a_list = [.15]
        self.p.amp_tweezer_list = a_list

        # self.xvar('x_tweezer_move',np.linspace(.6e-6,1.2e-6,5))
        self.p.x_tweezer_move = .9e-6
        # self.xvar('t_tweezer_move',np.linspace(5.e-3,30.e-3,25))
        self.p.t_tweezer_move = 15.e-3

        # self.xvar('t_tof',np.linspace(1000.,3000.,10)*1.e-6)

        # self.xvar('hf_imaging_detuning', np.arange(-650.,-500.,8.)*1.e6)
        # self.p.hf_imaging_detuning = -602.e6 # 190.
        # self.p.hf_imaging_detuning = -609.e6 # 192.
        self.p.hf_imaging_detuning = -615.e6 # 193.2
        # self.p.hf_imaging_detuning = -562.e6 # 182.

        # self.xvar('t_imaging_pulse',np.linspace(10.,500.,10)*1.e-6)
        # self.p.t_imaging_pulse = 20.e-6    
        
        self.camera_params.exposure_time = 25.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.

        # self.xvar('amp_imaging', np.linspace(.1,.4,15))
        # self.p.amp_imaging = .35
        # self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 700
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_evap2_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.tweezer.traps[0].set_frequency(f=self.p.ce_frequency)
        delay(10.e-3)

        self.tweezer.traps[0].cubic_move(self.p.t_tweezer_move,x_move=self.p.x_tweezer_move,trigger=False)
        delay(100.e-3)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,self.p.v_yshim_current_magtrap,0.,n=500)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                             i_start=0.,
                             i_end=self.p.i_hf_lightsheet_evap1_current)
        
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
        
        self.tweezer.trigger()
        delay(self.p.t_tweezer_move)
        delay(1.e-3)

        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

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
