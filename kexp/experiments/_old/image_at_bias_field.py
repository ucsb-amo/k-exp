from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config import camera_params
from kexp.util.artiq.async_print import aprint

import numpy as np

class image_at_bias_field(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.N_repeats = [1,1]
        self.p.t_mot_load = 0.25

        self.p.amp_imaging_abs = 0.26
        self.p.t_imaging_pulse = 5.e-6

        # self.p.t_tof = np.linspace(1000,1500,N) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(4000,6000,N) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(5000,7000,N) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(9023,13368,N) * 1.e-6 # gm
        self.p.t_tof = 10 * 1.e-6
        # self.p.t_tof = np.linspace(100,20368,N) * 1.e-6
        # self.p.t_tof = np.linspace(100.,700.,N) * 1.e-6
        # self.p.t_tof = np.linspace(14000.,17000.,N) * 1.e-6

        # self.p.img_detuning = self.p.frequency_detuned_imaging + np.linspace(-40,5,15) * 1.e6
        self.p.img_detuning = self.p.frequency_detuned_imaging + np.linspace(-40,5,40) * 1.e6

        self.p.xvar_v_zshim_current_op = np.linspace(0.,8.00,4)

        # self.p.mag_trap_bool = np.array([0,1])

        # self.p.frequency_detuned_imaging_F1 = self.p.frequency_detuned_imaging + 461.7e6

        self.xvarnames = ['img_detuning','xvar_v_zshim_current_op']

        self.finish_prepare()

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.set_imaging_detuning(detuning=self.p.frequency_detuned_imaging_F1)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for img_detuning in self.p.img_detuning:
            for vshim in self.p.xvar_v_zshim_current_op:

                self.set_imaging_detuning(img_detuning)
                self.mot(self.p.t_mot_load * s)
                self.dds.push.off()
                self.cmot_d1(self.p.t_d1cmot * s)
                self.gm(self.p.t_gm * s)
                self.gm_ramp(self.p.t_gmramp * s)
                self.release()
                self.flash_repump()

                self.ttl.machine_table_trig.on()
                self.set_zshim_magnet_current(v=vshim)
                delay(10.e-3)
                self.ttl.machine_table_trig.off()

                self.optical_pumping(t=100.e-6,t_bias_rampup=0.,v_zshim_current=vshim)

                # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

                # delay(25.e-3)
                # self.lightsheet.off()

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