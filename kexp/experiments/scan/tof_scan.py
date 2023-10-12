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

        self.p.t_tof = np.linspace(6000.,8500.,5) * 1.e-6
        self.p.xvar_amp_d2_r_mot = np.linspace(.05,.188,5)
        # self.p.t_mot_load = np.linspace(0.3,1.2,6)

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['xvar_amp_d2_r_mot','t_tof']

        self.p.N_repeats = [1,1]

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for r in self.p.xvar_amp_d2_r_mot:
            for t in self.p.t_tof:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, amp_d2_r=r)
                # self.hybrid_mot(self.p.t_mot_load * s)

                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                # self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)
                self.trig_ttl.off()

                # self.gm_ramp(self.p.t_gmramp * s)

                # self.mot_reload(self.p.t_mot_reload * s)
                
                self.release()
                
                ### abs img
                delay(t * s)
                # self.fl_image()
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")