from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class ramsey(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        ### 

        self.p.t1 = 0.
        # self.p.t2 = 0.
        self.xvar('t2',np.linspace(0.,100.e-6,35))
        self.xvar('amp_pci',np.linspace(0.,0.13,10))

        self.p.t_pci_pulse = 3.e-6
        self.p.amp_pci = 0.1
        

        # self.xvar('y',[0,1] )

        self.p.frequency_tweezer_list = [74.e6]
        self.p.amp_tweezer_list = [.99]
        self.p.t_mot_load = 1.
        self.p.t_tof = 300.e-6
        self.p.N_repeats = 10

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.set_imaging_detuning(self.p.frequency_detuned_imaging_midpoint,
                                  amp=self.p.amp_pci)

        # prepare tweezers and raman beams
        self.prepare_lf_tweezers()
        self.init_raman_beams() 
        # prepare 1,0
        self.pi_pulse()

        # start spin echo sequence
        self.hadamard()

        delay(self.p.t1)

        self.pci_pulse(self.p.t_pci_pulse)

        delay(self.p.t2)

        self.pci_pulse(self.p.t_pci_pulse)

        delay(self.p.t1)

        self.hadamard()

        self.pi_pulse()

        self.set_imaging_detuning(self.p.frequency_detuned_imaging_0)
        delay(10.e-3)
        
        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

    @kernel
    def pci_pulse(self,t):
        self.dds.imaging.on()
        delay(t)
        self.dds.imaging.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

        self.shutdown_sources()