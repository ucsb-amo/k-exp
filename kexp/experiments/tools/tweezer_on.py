from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning
from artiq.coredevice.sampler import Sampler
from artiq.language import now_mu

class TweezerOn(EnvExperiment, Base):
    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.finish_prepare()
    
        # add tweezers by adding frequencies within 75.e6 +/- 4.e6
        self.p.frequency_tweezer_list = [75.e6]
        
        # make sure number of amps match number of tweezers, amps should sum to </= 1.
        self.p.amp_tweezer_list = [.18]

        # painting amplitude runs from -7. to 6 V
        self.p.v_hf_tweezer_paint_amp_max = -2.

        # tweezer rampup endpoint (0 - 9. V)
        self.p.v_pd_hf_tweezer_1064_ramp_end = 1.

    @kernel
    def scan_kernel(self):
        self.tweezer.on()

        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False)
        
        # delay(1.)
        # self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()