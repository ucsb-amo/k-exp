"""Forces an RTIOUnderflow in scan_kernel, to check the scan loop's abort path:
cleanup_scan_kernel runs first, then the ORIGINAL exception is re-raised, so the
core-device traceback names the channel, the timestamp and this file's line.

No atoms, no imaging, nothing saved (save_data=False), camera not set up (the
APD stage is not moved).  One shot: wait until the RTIO counter reaches the
timeline cursor, then pulse a TTL at that (now past) time.
"""
from artiq.experiment import *
from artiq.language.core import now_mu
from kexp import Base, cameras


class underflow_traceback_test(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.xy_basler,
                      setup_camera=False,
                      save_data=False)
        self.finish_prepare(shuffle=False)

    @kernel
    def scan_kernel(self):
        self.core.wait_until_mu(now_mu())
        self.ttl.pd_scope_trig3.pulse(1.e-6)   # timestamp already in the past -> RTIOUnderflow

    @kernel
    def run(self):
        self.init_kernel()
        self.scan()

    def analyze(self):
        import os
        self.end(os.path.abspath(__file__))
