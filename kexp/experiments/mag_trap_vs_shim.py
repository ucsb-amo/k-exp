from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class magtrap_vs_shim(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mag trap out of gm, image in-situ"

        ## Parameters

        self.p = self.params

        self.p.t_mot_load = 0.5

        self.p.t_tof = 10.e-6

        self.p.t_magtrap_on = np.linspace(1.,25.,6) * 1.e-3
        # self.p.t_magtrap_on = 11.e-3

        self.p.v_magtrap = np.linspace(3.0,9.99,6)

        # self.p.xvar_v_xshim = np.linspace(0.0,2.5,7)
        # self.p.xvar_v_yshim = np.linspace(0.0,2.5,7)

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        # self.xvarnames = ['t_magtrap_on','xvar_v_xshim']
        self.xvarnames = ['xvar_v_yshim','xvar_v_xshim']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        # for vy in self.p.xvar_v_yshim:
        #     for vx in self.p.xvar_v_xshim:
        for t_mag in self.p.t_magtrap_on:
            for v_mag_trap in self.p.v_magtrap:

                # self.mot(self.p.t_mot_load * s, v_yshim_current=vy, v_xshim_current=vx)
                self.mot(self.p.t_mot_load)

                self.dds.push.off()
                
                self.ttl.pd_scope_trig.on()
                self.cmot_d1(self.p.t_d1cmot * s)

                self.gm(self.p.t_gm * s)

                self.gm_ramp(self.p.t_gmramp * s)
                self.ttl.pd_scope_trig.off()

                self.switch_d1_3d(0)

                self.set_magnet_current(v=v_mag_trap)
                self.ttl.magnets.on()
                delay(t_mag)
                self.ttl.magnets.off()

                ### abs img
                delay(self.p.t_tof * s)
                # self.fl_image()
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

                self.set_magnet_current(v=self.p.v_mot_current)
                delay(0.1)
                
                delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")