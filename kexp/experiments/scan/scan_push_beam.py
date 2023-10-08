from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

class scan_push(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "optimize push beam power, detuning"

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 2

        self.p.t_tof = 1100.e-6

        self.p.xvar1_detune_push = np.linspace(-2.5,1.,5)
        self.p.xvar2_amp_push = np.linspace(0.09,0.18,5)

        self.trig_ttl = self.get_device("ttl14")
        
        self.xvarnames = ['xvar1_detune_push','xvar2_amp_push']

        self.shuffle_xvars()
        self.get_N_img()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)
        for d_push in self.p.xvar1_detune_push:
            for a_push in self.p.xvar2_amp_push:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s, detune_push=d_push, amp_push=a_push)

                self.dds.push.off()

                # self.cmot_d1(self.p.t_d1cmot * s)

                # self.trig_ttl.on()
                # self.gm(self.p.t_gm * s)

                # self.gm_ramp(self.p.t_gmramp * s)
                # self.trig_ttl.off()
                
                self.release()

                delay(self.p.t_tof)

                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.p.detune_push = self.p.xvar1_detune_push
        self.p.amp_push = self.p.xvar2_amp_push

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")