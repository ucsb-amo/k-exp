import numpy as np
from artiq.experiment import *
from kexp import Base, img_types, cameras
from artiq.language import now_mu, at_mu, delay

class hf_raman(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      camera_select=cameras.andor,
                      save_data=True,
                      imaging_type=img_types.ABSORPTION)
        
        # self.xvar('t_raman_pulse', np.linspace(0.,25.,20)*1.e-6)
        # self.p.t_raman_pulse = 5.e-6

        self.p.t_raman_pulse_list = np.linspace(1,10.,10) * 1.e-6

        self.p.t_tof = 100.e-6
        self.p.N_repeats = 10

        self.scope = self.scope_data.add_siglent_scope("192.168.1.108", label='PD', arm=False)

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        
        self.raman.off()

        self.prep_raman(fraction_power=.05)
        
        t = now_mu()
        self.ttl.pd_scope_trig3.pulse(1.e-6)
        at_mu(t)

        for dt in self.p.t_raman_pulse_list:
            self.raman.pulse(dt)
            delay(10.e-6)

        self.ttl.raman_shutter.off()

        self.core.wait_until_mu(now_mu())
        b = self.scope.read_sweep([2])
        self.core.break_realtime()
        delay(500.e-3)

    @kernel
    def run(self):
        b = True
        self.init_kernel(setup_slm=False,
                         setup_awg=False,
                         init_sampler=False)
        self.scan()
        
    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)