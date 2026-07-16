from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=True)

        self.xvar('dummy',[0]*2)
        self.xvar('dummy2',[0]*3)

        self.data.test2d = self.data.add_data_container(per_shot_data_shape=(10,5), dtype=np.float64)
        self.data.test1d = self.data.add_data_container(per_shot_data_shape=5, dtype=np.float64)
        self.data.int1d = self.data.add_data_container(per_shot_data_shape=(5,), dtype=np.int64)

        # print(type(self.data.test2d))
        print(type(self.data.test1d))

        self.x = np.random.random((10,5))
        self.y = np.random.random(5)
        self.z = (np.random.random(5)*100).astype(np.int64)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.data.test2d.put_data_array(self.x)
        self.data.test1d.put_data_row(self.y)
        self.data.int1d.put_data_row(self.z)

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)