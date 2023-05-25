from kexp import Base
from artiq.experiment import *
from artiq.experiment import delay, kernel, parallel

class ramp_test(EnvExperiment,Base):
    def build(self):
        Base.__init__(self,setup_camera=False)
        self.ttl = self.get_device("ttl8")

        self.t_ramp = 10.e-6
        self.amp_i = 0.2

    @kernel
    def run(self):
        self.init_kernel()

        delay(10*ms)

        # self.gm_ramp_setup(self.t_ramp,self.amp_i,self.amp_i,10)

        delay(10*ms)

        self.dds.d1_3d_c.on()
        self.dds.d1_3d_r.on()

        delay(1*ms)

        
        self.gm_ramp(self.t_ramp)
        self.ttl.on()
        delay(1*ms)
        
        
        # # with parallel:
        # self.dds.enable_profile()
        # self.ttl.on()

        # delay(self.t_ramp * 2)

        # with parallel:
        #     self.dds.disable_profile()
        #     self.ttl.off()

        self.ttl.off()
        self.dds.d1_3d_c.off()
        self.dds.d1_3d_r.off()
            