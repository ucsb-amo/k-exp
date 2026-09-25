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

        self.xvar('make_atoms',[0,1,2])

        self.p.t_tweezer_hold = 100.e-3
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        if self.p.make_atoms == 2:
            self.imaging.set_power(0.05)
        else:
            self.imaging.set_power(2.)

        if self.p.make_atoms == 1:
            self.prepare_hf_tweezers()
        else:
            delay(1.)

        delay(10.e-3)
 
        # ###
        self.handoff_to_quantum_machines()
        # ###
        self.wait_for_quantum_machines_handback()

        delay(10.e-3)

        self.tweezer.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)