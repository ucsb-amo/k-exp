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
        self.p.t_tof = 20.e-6
        # self.xvar('t_tof',np.linspace(400.,3000.,10)*1.e-6) 
        # self.xvar('dumy',[0.]*3)
    
        # self.xvar('hf_imaging_detuning', [-617.e6,-505.e6]*1)

        # self.p.t_magtrap = .5

        # self.xvar('t_feshbach_field_rampup',np.linspace(.02,.3,8))
        # self.p.t_feshbach_field_rampup = 100.e-3

        # self.xvar('t_magtrap_rampdown',np.linspace(15.,200.,8)*1.e-3)
        # self.p.t_magtrap_rampdown = 41.e-3

        # self.xvar('i_hf_lightsheet_evap1_current',np.linspace(186.,194.,8))
        # self.p.i_hf_lightsheet_evap1_current = 195.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.3,1.,20))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .55

        # self.xvar('t_hf_lightsheet_rampdown',np.linspace(100.,1500.,20)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown = .45

        # self.xvar('t_hf_lightsheet_rampdown2',np.linspace(10.,60.,15)*1.e-3)
        # self.p.t_hf_lightsheet_rampdown2 = .02

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.5,194.,10))
        # self.p.i_hf_tweezer_load_current = 193.1

        # self.p.i_image_current = 190.
 
        # self.xvar('v_pd_hf_tweezer_1064_ramp_end',np.linspace(3.,9.5,10))
        # self.p.v_pd_hf_tweezer_1064_ramp_end = 9.5

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-3.,.5,15))
        # self.p.v_hf_tweezer_paint_amp_max = -2.
# 
        # self.xvar('t_hf_tweezer_1064_ramp',np.linspace(.02,1.,15))
        # self.p.t_hf_tweezer_1064_ramp = .23

        self.xvar('i_hf_squeeze1_current',np.linspace(182.,194.,10))
        self.p.i_hf_squeeze1_current = 193.47

        # self.xvar('i_tunnel',np.linspace(180.,190.,20)) 
        self.p.i_tunnel = 182. 

        # self.xvar('t_tweezer_hold',np.linspace(0.,10.,5)*1.e-3)
        self.p.t_tweezer_hold = .1e-3

        self.xvar('hf_imaging_detuning', np.arange(-630.,-550.,5.)*1.e6)
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
        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_load_current)
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
                          
        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                             i_start=self.p.i_hf_tweezer_load_current,
                             i_end=self.p.i_hf_squeeze1_current)
        
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