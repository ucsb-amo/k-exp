from artiq.experiment import *
from kexp import Base

class test(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False,save_data=False)
        self.finish_build()

    @kernel
    def run(self):
        self.init_kernel()

        # self.ttl.pd_scope_trig.pulse(1.e-6)
        # self.shuttler.tweezer_fm.linear_ramp(t=50.e-3,v_start=1.,v_end=0.)
        # self.on()







        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.shuttler.tweezer_fm.sine(frequency=1/(5.e-3),v_amplitude=1.,v_offset=1.)
        delay(50.e-3)
        self.shuttler.tweezer_fm.off()
        
        