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
        self.p.t_delay = np.linspace(2,13,10) * 1.e-3

        self.xvarnames = ['t_delay']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()
        
        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        for t in self.p.t_delay:

            self.kill_mot(self.p.t_mot_kill * s)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)
            
            ### Turn off 2d MOT, Repump, and 3D MOT###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s)

            ###ODT on
            self.dds.lightsheet.set_dds(v_pd=5.)
            self.dds.lightsheet.on()

            # self.gm_ramp(self.p.t_gmramp * s)

            delay(10.e-3)

            self.switch_d1_3d(0)

            delay(t * s)

            self.release()

            self.dds.lightsheet.off()

            ### abs img
            delay(100.e-6)
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")





