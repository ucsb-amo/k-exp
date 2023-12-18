from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class image_at_bias_field(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = 1
        self.p.t_mot_load = 0.25

        self.p.amp_imaging_abs = 0.26
        self.p.t_imaging_pulse = 5.e-6
        self.p.t_tof = 8.e-3

        self.p.t_rabi_flop = np.linspace(0.,120.,30) * 1.e-6

        self.xvarnames = ['t_rabi_flop']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)


        for t_flop in self.p.t_rabi_flop:
            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s)
            self.release()

            self.dds.d1_3d_c.set_dds_gamma(self.p.detune_d1_c_gm,v_pd=5.0)
            self.dds.d1_3d_r.set_dds_gamma(self.p.detune_d1_r_gm,v_pd=5.0)

            self.set_zshim_magnet_current(v=9.99)
            delay(7.e-3)

            self.flash_repump()

            if t_flop:
                with parallel:
                    self.dds.d1_3d_c.dds_device.sw.on()
                    self.dds.d1_3d_r.dds_device.sw.on()
                delay(t_flop)
                with parallel:
                    self.dds.d1_3d_c.dds_device.sw.off()
                    self.dds.d1_3d_r.dds_device.sw.off()

            ### abs img
            delay(self.p.t_tof * s)
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