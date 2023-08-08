from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class mot_cone(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,absorption_image=False,basler_imaging=True)
        # Base.__init__(self,setup_camera=False)

        self.run_info._run_description = "gm with fluorescence camera"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 3
        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(500,10000,self.p.N_shots) * 1.e-6

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        self.dds.tweezer.on()
        
        for t_tof in self.p.t_tof:

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            self.trig_ttl.on()
            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)
            self.trig_ttl.off()

            delay(t_tof)

            self.fl_image_old()
            
            self.release()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")