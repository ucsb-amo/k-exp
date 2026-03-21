from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd2_to_vpd1

class squeezeme(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        self.p.squeeze = 1
        # self.xvar('squeeze',[0,1])
        
        self.p.t_tweezer_squeezer_ramp_1 = 10.e-3
        self.p.t_tweezer_squeezer_ramp_2 = 10.e-3

        self.p.v_pd_tweezer_squeeze_rampup_handoff_lp = 9.

        # self.p.v_pd_hf_tweezer_squeeze_power = 0.5
        self.xvar('v_pd_hf_tweezer_squeeze_power', np.linspace(
            tweezer_vpd2_to_vpd1(self.p.v_pd_tweezer_squeeze_rampup_handoff_lp),0.5,3))

        # self.p.t_tweezer_hold = 10.e-3
        # self.xvar('t_tweezer_hold', np.linspace(1.,100.,5)*1.e-3)

        self.p.amp_imaging = self.camera_params.amp_imaging
        self.camera_params.gain = 600

        self.p.t_tof = 5.e-6
        self.xvar('t_tof',np.linspace(5.,150.,5)*1.e-6)
        self.p.N_repeats = 1

        # self.p.t_ramp_down_painting_amp = 15.e-3
        # self.xvar('t_ramp_down_painting_amp',np.linspace(1.,100.,4)*1.e-3)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging)

        self.prepare_hf_tweezers()
        if self.p.squeeze:
            self.tweezer_squeeze()

        self.ttl.pd_scope_trig.pulse(1.e-6)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)