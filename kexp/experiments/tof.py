from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,camera_select='xy_basler')

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.0

        # self.p.amp_imaging_abs = 0.3

        # self.p.t_magnet_off_pretrigger = 1.e-3

        self.p.t_gm = 4.5e-3

        # self.p.t_tof = np.linspace(20,500,6) * 1.e-6 # mot

        self.p.t_hold = np.linspace(.05,30,6) * 1.e-3

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        self.xvarnames = ['t_hold']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        print('hi')

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t in self.p.t_hold:

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.set_shims(v_zshim_current=.84, v_yshim_current=self.p.v_yshim_current, v_xshim_current=self.p.v_xshim_current)
            self.gm(self.p.t_gm * s)
            # self.gm_ramp(self.p.t_gmramp * s)
            self.release()

            # self.dds.mot_killer.on()

            

            # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
            # delay(t)
            
            
            # self.ttl.pd_scope_trig.on()
            self.tweezer.ramp(t=10.e-3)
            delay(t)
            self.tweezer.off()
            # self.ttl.pd_scope_trig.off()

            

            # self.optical_pumping(t=)

            ### abs img
            delay(15.e-6 * s)
            # delay(100.e-6 * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            # self.dds.mot_killer.off()

            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")