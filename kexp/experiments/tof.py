from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 1
        self.p.t_mot_load = 1.0

        # self.p.amp_imaging_abs = 0.26

        self.p.t_magnet_off_pretrigger = 1.e-3
        self.p.t_gm = 2.5e-3

        # self.p.t_tof = np.linspace(500,1500,N) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(4000,6000,N) * 1.e-6 # d1 cmot
        self.p.t_tof = np.linspace(12000,18000,5) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(9023,13368,N) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(100,20368,N) * 1.e-6
        # self.p.t_tof = np.linspace(100.,700.,N) * 1.e-6
        # self.p.t_tof = np.linspace(14000.,17000.,N) * 1.e-6

        # self.p.mag_trap_bool = np.array([0,1])

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        self.xvarnames = ['t_tof']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for t_tof in self.p.t_tof:

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.ttl.pd_scope_trig.on()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.set_shims(v_zshim_current=.84, v_yshim_current=self.p.v_yshim_current, v_xshim_current=self.p.v_xshim_current)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s)
            self.release()

            # self.set_magnet_current(v=5.)
            # self.ttl.magnets.on()
            # delay(t_tof * s)
            # self.ttl.magnets.off()

            # self.lightsheet.ramp(t_ramp=self.p.t_lightsheet_rampup)

            # delay(25.e-3)
            # self.lightsheet.off()

            # self.optical_pumping(t=)

            ### abs img
            delay(t_tof * s)
            self.ttl.pd_scope_trig.off()
            # delay(100.e-6 * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")