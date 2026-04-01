from artiq.experiment import *
from kexp import Base, img_types, cameras
import numpy as np

class complex_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      imaging_type=img_types.DISPERSIVE)
        
        self.sigma_x = np.array([[0,1],[1,0]], dtype=complex)
        self.sigma_y = np.array([[0,-1j],[1j,0]], dtype=complex)
        self.sigma_z = np.array([[1,0],[0,1]], dtype=complex)
        self.I = np.array([[1,0],[0,1]], dtype=complex)
        self.finish_prepare()


    @kernel
    def scan_kernel(self):
        np.matmul(self.sigma_x, self.sigma_y)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)