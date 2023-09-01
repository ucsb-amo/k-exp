from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = ""

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.N_repeats = [1,3]
        self.p.t_gm = 1.e-3
        self.p.t_tof = 4000.e-6
        self.p.xvar2_t = np.linspace(3000,7000,4) * 1.e-6 # gm
        self.p.xvar_t = np.linspace(3.,6.,5) * 1.e-3
        self.p.n_gmramp_steps = 100

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['xvar_t','t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t in self.p.xvar_t:
            for t2 in self.p.xvar_t2:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(t * s)
                self.trig_ttl.off()

                # self.gm_ramp(t2 * s)

                # self.mot_reload(self.p.t_mot_reload * s)
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                # self.fl_image()
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.t_gm = self.p.xvar_t

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")