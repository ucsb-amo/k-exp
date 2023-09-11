from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class light_sheet_mot_recapture(EnvExperiment, Base):
    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)
        self.run_info._run_description = "load MOT, ODT on, MOT off, "

        self.p = self.params

        self.p.N_shots = 6
        self.p.t_tof = np.linspace(1000,2100,6) * 1.e-6
        # self.p.t_tof = 1000 * 1e-6
        self.p.v_pd_lightsheet = np.linspace(1.,4.5,5)
        # self.p.v_pd_lightsheet = 5.

        self.xvarnames = ['v_pd_lightsheet','t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()
        
        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        for v in self.p.v_pd_lightsheet:
            for t in self.p.t_tof:

                self.kill_mot(self.p.t_mot_kill * s)

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ###ODT on
                # self.dds.lightsheet.set_dds(v_pd=self.p.v_pd_lightsheet)
                self.dds.lightsheet.set_dds(v_pd=v)
                self.dds.lightsheet.on()

                delay(100.e-3)

                ### Turn off 2d MOT, Repump, and 3D MOT###
                self.dds.push.off()
                self.switch_d2_2d(0)
                self.release()

                ### abs img
                delay(t * s)
                self.flash_repump()
                self.abs_image()

                self.dds.lightsheet.off()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")





