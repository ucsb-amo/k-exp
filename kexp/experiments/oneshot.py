from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class oneshot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "oneshot"

        ## Parameters

        self.p = self.params

        self.p.N_shots = 2
        self.p.N_repeats = 1
        self.p.t_tof = np.linspace(1000.,1000.,self.p.N_shots) * 1.e-6

        self.xvarnames = ['t_tof']

        self.shuffle_xvars()
        self.get_N_img()

        self.p.t_d1cmot = 3.e-3

        self.p.t_andor_expose = 5. * 1.e-3

    # @kernel
    # def andor_img(self):
    #     delay(-self.p.t_andor_expose*s)
    #     self.ttl_andor.pulse(self.p.t_andor_expose*s)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)
        # self.ttl_andor.pulse(self.p.t_andor_expose*s)
        
        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            
            self.mot(self.p.t_mot_load * s)
            # self.ttl_andor.pulse(self.p.t_andor_expose*s)
            # self.hybrid_mot(self.p.t_mot_load * s)
            

            self.dds.push.off()
            self.switch_d2_2d(0)
            
            
            self.cmot_d1(self.p.t_d1cmot * s)
            
            
            self.gm(self.p.t_gm * s)
            self.ttl_andor.pulse(self.p.t_andor_expose*s)
            
            # self.gm_ramp(self.p.t_gm_ramp * s)
            
            self.release()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")