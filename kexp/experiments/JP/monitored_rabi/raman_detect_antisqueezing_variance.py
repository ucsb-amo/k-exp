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


        self.p.i_hf_raman = 182.

        self.p.t_raman_sweep = 1.e-3
        self.p.frequency_raman_sweep_center = 147.265e6
        self.p.frequency_raman_sweep_width = 10.e3
        self.p.frequency_raman_transition = 147.2489e6 # 182. A

        self.p.t_raman_pi_pulse = 4.9070e-6

        self.p.fraction_power_raman = .5
        
        self.p.amp_imaging_abs = .2
        self.p.amp_imaging_pci = .1

        self.p.t_pci_measurement = 20.e-6

        self.p.t_tof = 1000.e-6
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_midpoint)
        self.imaging.set_power(self.p.amp_imaging_pci)

        self.prepare_hf_tweezers()

        self.raman.init(frequency_transition = self.p.frequency_raman_transition, 
                        fraction_power = self.params.fraction_power_raman)
        
        self.ttl.raman_shutter.on()
        delay(10.e-3)
        self.ttl.line_trigger.wait_for_line_trigger()
        delay(4.7e-3)

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)
        self.imaging.pulse(self.p.t_pci_measurement)
        self.raman.pulse(self.p.t_raman_pi_pulse)
        self.imaging.pulse(self.p.t_pci_measurement)

        ####

        self.raman.set_phase(np.pi/2) # now y rotations
        self.raman.pulse(self.p.t_raman_pi_pulse / 2)
        self.raman.set_phase(0)

        ####

        self.raman.pulse(self.p.t_raman_pi_pulse / 2)

        self.ttl.raman_shutter.off()

        delay(self.p.t_tweezer_hold)

        # set up weak measurement
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        self.imaging.set_power(self.p.amp_imaging_abs)

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