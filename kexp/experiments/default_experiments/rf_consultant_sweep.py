"""Example: scan the 980 EO frequency, walking between shots.

Each shot starts with ``self.ry_980.sweep_to(...)``, which walks the EO's
frequency source from the frequency it reports to this shot's value in 0.5 MHz
steps 0.1 s apart, so a shuffled scan never jumps the laser.  The same code
runs on the Siglent or the RF consultant: which one is ``RY_980_RF`` in
kexp/base/devices.py.  The rest of the shot is a plain MOT TOF to stand in for
your sequence.

Before running it on the RF consultant:
  * ``RY_980_RF = 'rf_consultant'`` in kexp/base/devices.py, with the EO
    cabled to it,
  * ``rf_consultant_980`` assigned in beacon/beacon/tpi/rf_consultant_id.py, and
  * its TPI server up (Server Dashboard), on whichever PC it is plugged into.

End state: the RF output and amplitude are never touched.  The frequency is
left at the last scan value (post_scan walks ry_980 home only when the beam
was switched on; add ``self.ry_980.sweep_to(reset=True)`` after scan() for
that).  The same if the run stops on an exception.
"""
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, cameras


class rf_consultant_sweep(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      camera_select=cameras.xy_basler,
                      save_data=True)

        self.p.frequency_rf_980 = 417.e6        # Hz; scanned below
        self.xvar('frequency_rf_980', np.linspace(412., 422., 11) * 1.e6)

        self.p.t_tof = 1.e-3
        self.p.t_mot_load = 0.5
        self.p.N_repeats = 3

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        # Between shots: walk to this shot's frequency (blocks until there).
        self.ry_980.sweep_to(self.p.frequency_rf_980)

        self.dds.imaging.set_dds(amplitude=self.camera_params.amp_imaging)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.release()
        delay(self.p.t_tof)
        self.flash_repump()
        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel(setup_awg=False)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)
