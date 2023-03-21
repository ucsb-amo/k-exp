from artiq.experiment import *
from artiq.experiment import delay
from kexp.base.base import Base

class BigData(EnvExperiment,Base):
    def build(self):
        Base.__init__(self)

        self.params.N = 10

    @kernel
    def run(self):
        self.init_kernel()

        self.StartTriggeredGrab(self.params.N)
        delay(self.params.t_grab_start_wait * s)

        for i in range(self.params.N):
            # self.ttl_camera.pulse(self.params.t_camera_trigger)
            self.trigger_camera()
            delay(10*ms)

    def analyze(self):
        self.set_dataset("images",self.images)
        
