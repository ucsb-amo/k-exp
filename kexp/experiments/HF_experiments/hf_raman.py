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

        # self.xvar('v_pd_lightsheet_rampup_end',np.linspace(6.,9.,15))
        # self.p.v_pd_lightsheet_rampup_end = 7.

        # self.xvar('v_pd_hf_lightsheet_rampdown_end',np.linspace(.6,1.2,15))
        # self.p.v_pd_hf_lightsheet_rampdown_end = .8

        self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-4.,-1.,15))
        # self.p.v_hf_tweezer_paint_amp_max = -2.2

        # self.xvar('v_pd_hf_tweezer_1064_rampdown3_end',np.linspace(2.,5.,8))
        # self.p.v_pd_hf_tweezer_1064_rampdown3_end = 3.5

        # self.p.v_pd_hf_tweezer_squeeze_power = 3.94

        # self.p.i_hf_raman = 176.5

        # self.p.t_raman_sweep = 1.e-3
        # self.p.frequency_raman_sweep_center = 147.265e6
        # self.p.frequency_raman_sweep_width = 10.e3
        # self.xvar('frequency_raman_sweep_center', 119.39586237e6 + np.arange(-50.e3,50.e3,self.p.frequency_raman_sweep_width))

        # self.xvar('frequency_raman_transition',119.3978e6 + np.linspace(-1.e3,1.e3,10))
        # self.p.frequency_raman_transition = 147.2592e6 # 182. A -1 -2
        self.p.frequency_raman_transition = 119.3978e6 # 182 A -1 0

        # self.xvar('t_ramsey', np.linspace(10.e-6, 750.e-6, 5))
 
        # self.xvar('t_raman_pulse', [0.,self.p.t_raman_pi_pulse])
        # self.xvar('t_raman_pulse', np.linspace(0., 100., 60)*1.e-6)
        self.p.t_raman_pulse = self.p.t_raman_pi_pulse / 2 # -1 --> 0

        # self.xvar('fraction_power_raman',np.linspace(0., 0.5, 10))
        # self.p.fraction_power_raman = .0
        
        # self.xvar('hf_imaging_detuning', np.linspace(-600.e6,-535.e6,20))
        # self.p.hf_imaging_detuning = -543.8e6
        self.p.hf_imaging_detuning = -568.e6

        # self.xvar('amp_imaging',np.linspace(0.1,.8,10))
        self.p.amp_imaging = .2

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,300.e-3,10))
        self.p.t_tweezer_hold = .1e-3

        # self.xvar('t_tof',np.linspace(1000.,2800.,10)*1.e-6) 
        self.p.t_tof = 2200.e-6

        self.p.t_mot_load = 1.
        
        self.p.N_repeats = 1

        # self.camera_params.gain = 75.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # self.set_high_field_imaging(i_outer=self.p.hf_imaging_detuning)
        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        # self.slm.write_phase_mask_kernel(phase=self.p.phase_slm_mask)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers(ramp_down_painting=False,squeeze=False)

        # self.prep_raman(frequency_transition=self.p.frequency_raman_transition)

        # self.raman.pulse(self.p.t_raman_pulse)
        # delay(self.p.t_raman_pulse)

        # delay(self.p.t_ramsey)

        # self.raman.pulse(self.p.t_raman_pulse)

        # self.raman.sweep(t=self.p.t_raman_sweep,
        #                  frequency_center=self.p.frequency_raman_sweep_center,
        #                  frequency_sweep_fullwidth=self.p.frequency_raman_sweep_width,
        #                  n_steps=100)
        delay(1.e-3)
        # self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        # self.outer_coil.stop_pid()

        # self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel(setup_slm=True)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)