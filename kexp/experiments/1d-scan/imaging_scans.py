from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from artiq.language.core import now_mu

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_image_detuning(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self,setup_camera=True,andor_imaging=False,absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan image detuning"

        ## Parameters

        self.p = self.params

        self.p.t_tof = 1250 * 1.e-6 # mot
        
        # self.p.xvar_amp_imaging_abs = np.linspace(0.1,0.6,3)

        self.p.N_repeats = 1
        # self.p.xvar_frequency_detuned_imaging = np.linspace(25.,32.,15) * 1.e6
        # self.p.xvar_detune_repump_flash = np.linspace(-4.,4.,20)
        self.p.frequency_detuned_imaging_F1 = 461.7e6 + np.linspace(-14.,15.,12) * 1.e6

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['frequency_detuned_imaging_F1']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for xvar in self.p.frequency_detuned_imaging_F1:

            self.set_imaging_detuning(detuning=xvar)
            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            # self.flash_repump(detune=xvar)
            self.abs_image()

            self.core.break_realtime()

            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")