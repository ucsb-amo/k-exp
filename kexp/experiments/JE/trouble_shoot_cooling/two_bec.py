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
                      imaging_type=img_types.ABSORPTION)
        
        # self.p.v_pd_hf_tweezer_1064_rampdown2_end = .5
        # self.xvar('shot_number',np.linspace(1,400,400))

        # self.xvar('dumy',np.linspace(1.,100.,50))

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.,9.,15))
        # self.p.v_pd_lightsheet_rampup_end = 7.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.6,1.5,15))
        self.p.v_pd_hf_lightsheet_rampdown_end = 1.1

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.,195.,15))
        self.p.i_hf_tweezer_load_current = 192.5

        # self.xvar('i_hf_tweezer_evap1_current',np.linspace(192.,194.5,8))
        self.p.i_hf_tweezer_evap2_current = 192.9
        # self.xvar('i_hf_tweezer_evap2_current',np.linspace(192.5,194.5,8))
        self.p.i_hf_tweezer_evap2_current = 193.9
        
        # self.xvar('v_pd_hf_tweezer_1064_rampdown_end',np.linspace(.5,1.5,20))
        self.p.v_pd_hf_tweezer_1064_rampdown_end = .95

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-3.9,-2.,10))
        self.p.v_hf_tweezer_paint_amp_max = -3.6889

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(1.,4.,10))
        self.p.v_pd_hf_tweezer_1064_rampdown3_end = 1.75

        # self.p.v_pd_hf_tweezer_squeeze_power = 3.94

        # self.p.i_hf_raman = 193.

        self.p.frequency_tweezer_list=[74.6e6, 75.4e6]
        self.p.amp_tweezer_list = [0.19,0.2035]
        
        # self.xvar('hf_imaging_detuning', np.linspace(-630.e6,-600.e6,20))
        # self.p.hf_imaging_detuning = -619.e6

        # self.xvar('amp_imaging',np.linspace(0.1,.8,10))
        self.p.amp_imaging = .1

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = 10.e-3

        # self.xvar('t_tof',np.linspace(2000.,6000.,10)*1.e-6) 
        self.p.t_tof = 5700.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 200

        # self.camera_params.gain = 75.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_hf_tweezer_evap2_current)
        # self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(ramp_down_painting=False,squeeze=False)

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