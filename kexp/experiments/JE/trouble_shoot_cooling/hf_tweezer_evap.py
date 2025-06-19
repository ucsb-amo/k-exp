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
        
        self.p.t_tof = 50.e-6
        # self.xvar('t_tof',np.linspace(800.,4000.,20)*1.e-6) 
        self.xvar('dumy',[0]*3)

        # self.xvar('beans',[0,1]*10)
        
        self.p.t_lightsheet_hold = .2

        # self.p.t_magtrap = .5

        # self.xvar('t_feshbach_field_ramp',np.linspace(.07,.5,10))
        # self.p.t_feshbach_field_ramp = 100.e-3

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(190.,194.,8))
        # self.p.i_hf_lightsheet_evap1_current = 191.7

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.15,1.5,20))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .86

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,2000.,8)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = 1.2

        # self.xvar('t_hf_lightsheet_rampdown2',np.linspace(10.,60.,15)*1.e-3)
        self.p.t_hf_lightsheet_rampdown2 = .02

        # self.xvar('i_hf_tweezer_load_current',np.linspace(188.,193.,15))
        self.p.i_hf_tweezer_load_current = 190.5
 
        # self.xvar('v_pd_hf_tweezer_1064_ramp_end',np.linspace(4.,9.2,15))
        self.p.v_pd_hf_tweezer_1064_ramp_end = 6.2

        # self.xvar('v_tweezer_paint_amp_max',np.linspace(-6.,0.,15))
        self.p.v_tweezer_paint_amp_max = -3.

        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(.05,1.5,15))
        # self.p.t_hf_tweezer_1064_ramp = .5

        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.,195.,8))
        self.p.i_hf_tweezer_evap1_current = 193.3

        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(.1,2.,20))
        self.p.v_pd_hf_tweezer_1064_rampdown_end = 1.

        # self.xvar('t_hf_tweezer_1064_rampdown',np.linspace(20.,300.,15)*1.e-3) 
        self.p.t_hf_tweezer_1064_rampdown = 180.e-3        

        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(192.5,196.,20))
        self.p.i_hf_tweezer_evap2_current = 193.053

        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.07,.15,8))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .12

        # self.xvar('t_hf_tweezer_1064_rampdown2',np.linspace(200.,900.,8)*1.e-3) 
        self.p.t_hf_tweezer_1064_rampdown2 = 700.e-3  

        # self.xvar('i_hf_tweezer_evap3_current',np.linspace(192.5,196.,20))
        self.p.i_hf_tweezer_evap3_current = 193.42 

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(1.,2.5,10))
        self.p.v_pd_hf_tweezer_1064_rampdown3_end = 1.3

        # self.xvar('t_hf_tweezer_1064_rampdown3',np.linspace(200.,800.,10)*1.e-3) 
        self.p.t_hf_tweezer_1064_rampdown3 = 530.e-3   

        # self.xvar('t_tweezer_hold',np.linspace(0.,80.,15)*1.e-3)
        self.p.t_tweezer_hold = 1.e-3

        self.p.frequency_tweezer_list = [73.4e6,76.e6]
        # self.p.frequency_tweezer_list = np.linspace(76.e6,78.e6,6)
        # self.p.frequency_tweezer_list = [72.5e6]

        a_list = [.249,.25]
        self.p.amp_tweezer_list = a_list

        # self.xvar('t_tof',np.linspace(1200.,3300.,10)*1.e-6)

        # self.xvar('hf_imaging_detuning', np.arange(-620.,-595.,3.)*1.e6)

        # self.xvar('t_imaging_pulse',np.linspace(10.,500.,10)*1.e-6)
        # self.p.t_imaging_pulse = 20.e-6    
        
        # self.camera_params.exposure_time = 500.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        # self.camera_params.em_gain = 1.
        # self.xvar('hf_imaging_detuning', np.arange(-560.,-490.,5.)*1.e6)
        # self.p.hf_imaging_detuning = -560.e6

        # self.xvar('amp_imaging', np.linspace(.03,.2,20))
        # self.p.amp_imaging = .35
        self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_evap3_current)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

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
        
        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)
        
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
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown2,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                v_end=self.p.v_pd_lightsheet_rampdown2_end)

        self.lightsheet.off()
    
        # delay(self.p.t_lightsheet_hold)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_tweezer_evap2_current)
        
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          paint=True,keep_trap_frequency_constant=True)
        
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_evap2_current,
                             i_end=self.p.i_hf_tweezer_evap3_current)
        
        # delay(2.e-3)
        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # # tweezer evap 3 with constant trap frequency
        # self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)
        
        
        # delay(.2e-3)
        delay(self.p.t_tweezer_hold)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        # self.flash_repump()
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
