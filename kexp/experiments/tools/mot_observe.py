"""MOT Observe: puts the machine in its MOT-loading idle state.

init_kernel re-initializes every DDS (force_dds_init) and switches them all
off, and initializes the DAC, imaging, sampler, lightsheet, Rydberg lasers
and coils (both coils off).  Then Cooling.mot_observe: 3D MOT D2 light, the
2D MOT light and the push beam on at their ExptParams MOT settings, 3D D1 off,
the x/y/z shims and the 2D MOT supply at their ExptParams values, the INNER
COIL ON at i_mot, the outer coil off, and the imaging light on.  The tweezer
AWG, the SLM and the shuttler are not touched.

The Device Control GUI's "Run MOT Observe" button runs this file too (through
the monitor server, kexp.config.ip.RESET_STATE_EXPT_PATH; the button takes its
name from the title above): its end state replaces the device state file and
marks it trusted.
"""

from artiq.experiment import *
from kexp import Base
import os

import numpy as np

class mot_observe(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      setup_camera=False,
                      suppress_live_od=True)
        self.finish_prepare()

    @kernel
    def run(self):
        
        self.init_kernel(setup_awg=False,
                         setup_slm=False,
                         init_shuttler=False,
                         force_dds_init=True)
        delay(50*ms)
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, notify=False)
        print("Done!")