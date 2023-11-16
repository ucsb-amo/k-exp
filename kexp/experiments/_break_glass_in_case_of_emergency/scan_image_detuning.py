from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_image_detuning(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self,setup_camera=True,andor_imaging=False,absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan image amp vs pulse time"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.t_tof = 12000 * 1.e-6 # gm
        
        self.p.xvar_image_detuning = np.linspace(22.,28.,5) * 1.e6
        # self.p.frequency_detuned_imaging = 32.e6
        # self.p.xvar_amp_imaging_abs = np.linspace(0.1,0.3,3)
        self.p.xvar_t_imaging_pulse = np.linspace(2.,20.,5) * 1.e-6

        # self.camera_params.exposure_time = 8.0e-3

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['xvar_image_detuning','xvar_t_imaging_pulse']

        self.finish_build(shuffle=True)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_image_detuning:
            for xvar2 in self.p.xvar_t_imaging_pulse:

                self.p.t_imaging_pulse = xvar2
                self.set_imaging_detuning(detuning=xvar1)
                self.core.break_realtime()

                self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                self.gm_ramp(self.p.t_gmramp * s)
                self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                # self.flash_repump()
                self.abs_image()
                # self.fl_image()

                self.core.break_realtime()
                
                delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.p.t_imaging_pulse = self.p.xvar_t_imaging_pulse
        self.p.frequency_detuned_imaging = self.p.xvar_image_detuning

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")