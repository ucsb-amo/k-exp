"""Bare-ARTIQ baseline for startup_timer.py: no kexp, no waxx.

Gives the floor for import / compile / upload on this machine and core device.
The kernel only resets the RTIO core and returns -- no outputs are driven.

    art %code%\\k-exp\\kexp\\util\\profiling\\baseline_bare.py
"""

from artiq.experiment import *


class BaselineBare(EnvExperiment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def run(self):
        self.core.reset()
