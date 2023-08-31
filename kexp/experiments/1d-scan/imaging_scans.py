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

        self.p.t_tof = 100 * 1.e-6 # mot
        
        self.p.frequency_detuned_imaging = 32.e6
        # self.p.xvar_amp_imaging_abs = np.linspace(0.1,0.6,3)
        self.p.amp_imaging_abs = 0.2

        self.p.xvar_frequency_detuned_imaging = np.linspace(29.,34.,12) * 1.e6

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['xvar_frequency_detuned_imaging']

        self.finish_build(shuffle=True)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar in self.p.xvar_frequency_detuned_imaging:
            
            self.set_imaging_detuning(detuning=xvar)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)
            
            self.release()
            
            ### abs img
            delay(self.p.t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.frequency_detuned_imaging = self.p.xvar_frequency_detuned_imaging

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")