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
        Base.__init__(self,
                      camera_select=cameras.apd,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=0)

        self.xvar('dummy',0)

        self.p.t_tweezer_hold = 100.e-3
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(2.)
        # self.imaging.set_power(self.camera_params.amp_imaging)


        # self.prepare_hf_tweezers()

        delay(10.e-3)
 
        # ###
        self.handoff_to_quantum_machines()
        # ###
        self.wait_for_quantum_machines_handback()

        delay(10.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False,
                         init_shuttler=False,
                         init_ry=False,
                         init_magnets=False,
                         init_lightsheet=False,
                         init_sampler=False)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)