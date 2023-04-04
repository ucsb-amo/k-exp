from artiq.experiment import *
from kexp.base.base import Base
import numpy as np
from kexp.util.data.data_vault import DataSaver

class DataTestHDF5(EnvExperiment, Base):
    def build(self):
        Base.__init__(self,setup_camera=False)
        self.params.gamma = 3
        self.params.tof = np.linspace(0,10,5)
        self.xvarnames = ['tof']

        self.params.N_shots = 3*len(self.params.tof)

        self.images = np.ones((self.params.N_shots,10,10),dtype=int)
        self.image_timestamps = np.empty((self.params.N_shots,),dtype=int)

    @kernel
    def run(self):
        self.init_kernel()
        img = np.random.random((10,10))

        i = 0

        for t in self.params.tof:
            print(self.images[i])
            self.images[i] = img
            self.images[i] = img
            self.images[i] = img

            self.image_timestamps[i] = i
            i += 1
            self.image_timestamps[i] = i
            i += 1
            self.image_timestamps[i] = i
            i += 1

    def analyze(self):
        _ds = DataSaver()
        _ds.save_data_hdf5(self)
