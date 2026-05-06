from artiq.experiment import *
from artiq.language import delay, now_mu, at_mu
import numpy as np

from kexp import Base, img_types, cameras

class integrator_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.DISPERSIVE)
        
        self.finish_prepare()


    @kernel
    def run(self):

        self.init_kernel()

        self.core.break_realtime()

        self.raman.dds0.off()
        self.raman.dds1.off()

        self.prep_raman(frequency_transition=self.p.frequency_raman_transition,
                        phase_mode=1)
        delay(10.e-3)
        t = now_mu()
        self.raman.set(t_phase_origin_mu = t)
        delay(10.e-3)
        self.raman.dds0.on()
        self.raman.dds1.on()
        delay(10.e-3)
        self.raman.set_up_fast_frequency_update()
        delay(2.)
        self.raman.set_frequency_fast(self.p.frequency_raman_transition - 10.e6)
        # self.raman.set(self.p.frequency_raman_transition - 10.e6)
        delay(2.)
        self.raman.clean_up_fast_frequency_update()
        delay(1.)
        self.raman.dds0.off()
        self.raman.dds1.off()



        