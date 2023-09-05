from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class light_sheet(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tof = 10.e-6

        self.p.N_shots = 4
        self.p.N_repeats = 1
        self.p.t_test = 5.0e-3
        self.p.t_lightsheet_load = np.linspace(0.0,self.p.t_test,self.p.N_shots) * 1.e-3
        self.p.t_lightsheet_hold = 1.e-3

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['t_lightsheet_load']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t in self.p.t_lightsheet_load:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)
            self.trig_ttl.off()

            self.gm_ramp(self.p.t_gmramp * s)

            # delay(self.p.t_test - t)
            self.dds.light_sheet.on()
            delay(t)
            self.switch_d1_3d(0)
            # delay(self.p.t_lightsheet_hold)
            self.dds.light_sheet.off()

            ### abs img
            delay(self.p.t_tof * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")