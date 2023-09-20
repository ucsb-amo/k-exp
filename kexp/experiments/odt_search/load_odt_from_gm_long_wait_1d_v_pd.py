from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params

import numpy as np

class light_sheet_mot_recapture(EnvExperiment, Base):
    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)
        # self.camera_params.serial_no = camera_params.basler_fluor_camera_params.serial_no
        # self.camera_params.magnification = camera_params.basler_fluor_camera_params.magnification
        self.run_info._run_description = "load MOT, ODT on, MOT off, "

        self.p = self.params
        self.p.v_pd_lightsheet = np.linspace(0.,5.,10)

        self.xvarnames = ['v_pd_lightsheet']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()
        
        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        for v in self.p.v_pd_lightsheet:

            self.kill_mot(self.p.t_mot_kill * s)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off 2d MOT, Repump, and 3D MOT###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            ###ODT on
            self.dds.lightsheet.set_dds(v_pd=v)
            self.dds.lightsheet.on()

            self.gm(self.p.t_gm * s)

            # self.gm_ramp(self.p.t_gmramp * s)

            self.release()

            delay(12.e-3 * s)

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





