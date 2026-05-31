
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel, now_mu, at_mu
from kexp import Base, img_types, cameras

class ry_405_pulses(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)

        self.p.N_pulses = 1
        self.p.t_between_pulses = 200.e-3
        self.p.t_pulse = 100.e-3
        self.p.N_repeats = 1

        # self.xvar('v_pd_ry_405', np.linspace(0.5, 8.8, 5))
        # self.p.v_pd_ry_405 = 2.

        self.p.v_vva_ry_980 = 0.6
        # self.xvar('v_vva_ry_980', np.linspace(0.5, 9.99, 4))
        
        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):

        self.ry_980.set_power(self.p.v_vva_ry_980)

        delay(1.)

        self.ttl.pd_scope_trig3.pulse(1.e-6)

        for i in range(self.p.N_pulses):
            self.ry_980.on()
            delay(self.p.t_pulse)
            self.ry_980.off()
            delay(self.p.t_between_pulses)

        delay(4.)
        
        self.core.wait_until_mu(now_mu())
        # _ = self.scope.read_sweep(1)
        self.core.break_realtime()
        delay(30.e-3)

    @kernel
    def run(self):
        self.init_kernel(setup_slm=False,setup_awg=False)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
