from artiq.experiment import *
from artiq.language.core import delay, now_mu
from kexp import Base, cameras, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint

class lightsheet_from_magtrap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=False,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION)
        self._polmod_config = True

        self.xvar('kill',[0]*1)

        self.finish_prepare(shuffle=True)

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.imaging.init(frequency_polmod=1.9e6)
        # self.imaging.init(frequency_polmod=0.)
        self.scan()

    @kernel
    def scan_kernel(self):

        # self.dds.polmod_h.off()
        # self.dds.polmod_v.on()
        
        self.dds.imaging.set_dds(amplitude=0.5)
        self.ttl.imaging_shutter_x.on()
        delay(100.e-3)

        tau = 200.e-6
        T = 250.e-3
        dt = 1.e-6

        self.imaging.set_phase(0.,
                               0.,
                               t_phase_origin_mu=now_mu(),
                                 pretrigger=False)
        self.ttl.pd_scope_trig3.pulse(dt)
        self.ttl.pd_scope_trig.pulse(dt)
        # delay(-dt)
        # self.imaging.pulse(tau)
        self.imaging.on()
        delay(T)

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)