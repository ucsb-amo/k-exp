from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('v_pd_lf_tweezer_1064_rampdown2_end',np.linspace(.12,.4,10))
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = .25

        # self.xvar('do_split',[0,1]*10)
        self.p.do_split = 1

        self.tweezer.add_tweezer(frequency=75.6e6, amplitude=0.15)
        
        self.p.f_tweezer_mod = 5.e3
        self.p.x_tweezer_mod_amp = 2.2e-6

        self.xvar('t_mod_amp_ramp',np.linspace(5.,50.,10)*1.e-3)
        self.p.t_mod_amp_ramp = 25.e-3

        # self.xvar('t_tweezer_mod',np.linspace(25.,50.,10)*1.e-3)
        self.p.t_tweezer_mod = self.p.t_mod_amp_ramp + 5.e-3 # long enough to do the whole experiment

        # self.xvar('x_tweezer_mod_amp',np.linspace(.5,2.5,10)*1.e-6)

        self.p.t_mot_load = 1.
        self.p.t_tweezer_hold = .1e-3
        self.p.t_tof = 200.e-6

        self.camera_params.exposure_time = 20.e-6
        self.params.t_imaging_pulse = self.camera_params.exposure_time
        self.p.amp_imaging = .12
        
        self.p.N_repeats = 1
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.p.t_tweezer_mod = self.p.t_mod_amp_ramp

        if self.p.do_split:
            self.tweezer.traps[0].sine_move(t_mod=self.p.t_tweezer_mod,
                                x_mod=self.p.x_tweezer_mod_amp,
                                f_mod=self.p.f_tweezer_mod,
                                t_xmod_ramp=self.p.t_mod_amp_ramp,
                                trigger=False)
            delay(100.e-3)

        self.set_imaging_detuning(frequency_detuned = self.p.frequency_detuned_imaging_m1)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)
        delay(10.e-3)
        
        self.prepare_lf_tweezers()
        
        delay(self.p.t_tweezer_hold)

        if self.p.do_split:
            self.tweezer.trigger()
        delay(self.p.t_tweezer_mod)

        self.tweezer.off()
        delay(self.p.t_tof)
        self.abs_image()

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