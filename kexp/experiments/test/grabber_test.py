from artiq.experiment import *
from artiq.experiment import delay, TArray, TFloat
from artiq.language.core import now_mu
from kexp import Base, cameras, img_types
from kexp.control.artiq.TTL import TTL_OUT
import numpy as np

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False)
        self.camera_params = cameras.andor
        self.camera_params.select_imaging_type(imaging_type=img_types.ABSORPTION)
        self.ttl.camera = self.ttl.andor

        self.N = 1

        self.xvar('dum',[0]*self.N)

        self.grabber_data = np.array([0])

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False,
                         setup_awg=False,
                         init_dds=False,
                         init_dac=False,
                         init_shuttler=False,
                         init_lightsheet=False,
                         dds_set=False,
                         dds_off=False)
        self.core.reset()

        self.grabber.setup_roi(0,0,0,1,1)
        self.core.break_realtime()

        for _ in range(self.N):

            self.grabber.gate_roi(0b1)

            self.ttl.camera.pulse(1.e-6)

            self.grabber.input_mu(self.grabber_data,timeout_mu=now_mu()+np.int64(3.e9))

            self.core.break_realtime()
            self.grabber.gate_roi(0b0)
            
            delay(1.)

    def analyze(self):
        print(self.grabber_data)