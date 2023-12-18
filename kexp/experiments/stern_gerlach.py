from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params

import numpy as np

class sg(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "SG"

        ## Parameters

        self.p = self.params

        self.p.t_mot_load = 0.25

        self.p.N_repeats = 1

        # self.p.t_tof = np.linspace(1.,5.,8) * 1.e-3
        self.p.t_tof = 10.e-3
        self.p.v_bias = np.linspace(0.,1.00,3)
        self.p.v_sg_gradient = np.linspace(0.,5.,5)

        self.xvarnames = ['v_bias','v_sg_gradient']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        # for t_tof in self.p.t_tof:
        for v_bias in self.p.v_bias:
            for v_ah_grad in self.p.v_sg_gradient:

                self.mot(self.p.t_mot_load * s)
                self.dds.push.off()
                self.cmot_d1(self.p.t_d1cmot * s)
                self.gm(self.p.t_gm * s)
                self.gm_ramp(self.p.t_gmramp * s)
                self.release()
                self.flash_repump()

                self.set_zshim_magnet_current(v=v_bias)
                # self.optical_pumping(t=10.e-6,t_bias_rampup=0.)
                self.ttl.machine_table_trig.on()
                self.set_magnet_current(v=v_ah_grad)
                # delay(2.e-3)
                self.ttl.magnets.on()

                # ### abs img
                delay(self.p.t_tof * s)
                self.ttl.magnets.off()
                self.set_zshim_magnet_current(v=self.p.v_zshim_current)
                self.set_magnet_current()
                delay(5.e-3)
                # self.flash_repump()
                self.abs_image()
                self.ttl.machine_table_trig.off()

                self.core.break_realtime()

                delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")