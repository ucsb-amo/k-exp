from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)
        
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = .5
        # self.xvar('shot_number',np.linspace(1,400,400))

        # self.xvar('dumy',np.linspace(1.,100.,50))
        # self.xvar('frequency_detuned_imaging',np.linspace(-640.,-610.,20)*1.e6)
        self.p.frequency_detuned_imaging = -614.e6 

        self.p.v_pd_hf_lightsheet_rampdown_end = 1.0 # 0.85 #4.16
        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(.5,1.5,20))
        # self.p.v_pd_hf_tweezer_1064_rampdown_end = 6.
        self.p.i_hf_tweezer_load_current = 193.3 #91427+91428+91434, 2026-11-02  # six-knob evap bundle (193.0 equal in D2 91430), user OK
        # self.xvar('i_hf_tweezer_load_current',np.linspace(193.0,194.4,7))
        

        self.p.i_hf_tweezer_evap2_current =  193.9  #87461, 2026-10-20
        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(193.7,194.8,8))

        self.p.t_hf_tweezer_1064_rampdown2 = 0.3 #91427+91428+91434, 2026-11-02  # six-knob evap bundle, user OK
        # self.xvar('t_hf_tweezer_1064_rampdown2',np.linspace(0.1,0.9,8))

        self.p.t_hf_tweezer_1064_rampdown = 0.6 #91427+91428+91434, 2026-11-02  # six-knob evap bundle, user OK

        #self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(0.0,4.99,15))
        self.p.v_hf_tweezer_paint_amp_max = 1.6
       #self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.5,1.,11))
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = .8

        # self.xvar('amp_tweezer1', np.linspace(.2,.499,8))
        # self.xvar('amp_tweezer2', np.linspace(.2,.499,8))
        self.p.amp_tweezer1 = .49
        self.p.amp_tweezer2 = .49

        # self.xvar('frequency_tweezer1', np.linspace(74.2,74.99,5))
        # self.xvar('frequency_tweezer2', np.linspace(75.01,75.8,5))
        # self.xvar('frequency_diff_tweezer', np.linspace(.2,.45,20)*1.e6)
        self.p.frequency_diff_tweezer = .3e6
        self.p.frequency_tweezer1 = 74.5e6
        self.p.frequency_tweezer2 = 75.5e6

        self.p.frequency_tweezer_list=[74.5e6, 75.5e6]
        self.p.amp_tweezer_list = [0.49,.49]
        
        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = 5.e-3

        #self.xvar('t_tof',np.linspace(0.,5000.,20)*1.e-6) 
        self.p.t_tof = 3800.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 100

        # self.camera_params.gain = 75.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.tweezer.traps[0].set_amp(self.p.amp_tweezer1,trigger=True)
        delay(10.e-3)
        self.tweezer.traps[1].set_amp(self.p.amp_tweezer2,trigger=True)
        delay(10.e-3)
        self.tweezer.traps[0].set_frequency(75.e6 - self.p.frequency_diff_tweezer,trigger=True)
        delay(10.e-3)
        self.tweezer.traps[1].set_frequency(75.e6 + self.p.frequency_diff_tweezer,trigger=True)
        delay(10.e-3)

        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_evap2_current)
        # self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_imaging)

        self.prepare_hf_tweezers(magnet_PID=False)

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)