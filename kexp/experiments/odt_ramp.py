from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class light_sheet_mot_recapture(EnvExperiment, Base):
    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)
        self.run_info._run_description = "load MOT, ODT on, wait, MOT off, wait,MOT on and ODT off, abs img"

        self.p = self.params

        self.p.v_pd_lightsheet = 2

        N_interval = 1000
        self.p.v_pd_lightsheet = np.linspace(0,5,N_interval)

        self.xvarnames = ['light_sheet_amp']

        self.p.t_tof = 10.e-6

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()
        
        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)

        self.kill_mot(self.p.t_mot_kill * s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        self.mot(self.p.t_mot_load * s)
        # self.hybrid_mot(self.p.t_mot_load * s)

        ### Turn off push beam and 2D MOT to stop the atomic beam ###
        self.dds.push.off()
        self.switch_d2_2d(0)

        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp * s)

        for v in self.p.v_pd.lightsheet:
            self.dds.light_sheet.set_dds(v_pd=v)
            self.dds.light_sheet.on()
            delay()

        delay(1.e-3)

        self.release()

        ### abs img
        delay(t_tof * s)
        # self.fl_image()
        self.flash_repump()
        self.abs_image()

        self.core.break_realtime()

        



