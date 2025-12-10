from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_tof',np.linspace(100.,2000.,10)*1.e-6)
        self.p.t_tof = .5e-3
        
        # self.xvar('beans',[0,1]*50)

        # self.xvar('i_hf_tweezer_load_current',np.linspace(191.,194.,10))

        # self.xvar('v_hf_tweezer_paint_amp_max',np.linspace(-4.,2.5,15))
        self.p.v_lf_tweezer_paint_amp_max = -.286
        
        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end',np.linspace(.12,.3,15))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .21

        self.xvar('i_non_inter',np.linspace(180.3,181.,20))

        self.p.v_hf_paint_amp_end = -7.
        self.p.t_ramp_down_painting_amp = 100.e-3
        
        # self.xvar('amp_imaging',np.linspace(0.08,.54,10))
        # self.p.amp_imaging = .28
        # self.p.amp_imaging = .33

        # self.xvar('hf_imaging_detuning',np.linspace(-570.e6,-550.e6,5))
        self.p.hf_imaging_detuning = -563.e6 # 182. -1

        # self.xvar('t_tweezer_hold',np.linspace(1.e-3,1.1e-3,10))
        self.p.t_tweezer_hold = 20.e-3
        self.p.t_mot_load = 1.

        # self.camera_params.exposure_time = 20.e-6
        # self.params.t_imaging_pulse = self.camera_params.exposure_time
        
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned = self.p.hf_imaging_detuning)
        # self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        self.prepare_hf_tweezers()

        self.dac.tweezer_paint_amp.linear_ramp(t=self.p.t_ramp_down_painting_amp,
                                               v_start=self.dac.tweezer_paint_amp.v,
                                               v_end=self.p.v_hf_paint_amp_end,
                                               n=1000)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.outer_coil.stop_pid()

        self.outer_coil.off()

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