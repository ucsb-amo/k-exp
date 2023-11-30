from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint

import numpy as np

T_TOF_US = 20 # gm ramp
# T_TOF_US = 751 # mot
# T_TOF_US = 10 # light sheet
T_MOTLOAD_S = .9

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)
        
        # comment in/out to switch to abs imaging on x-axis
        # self.camera_params.serial_no = camera_params.basler_fluor_camera_params.serial_no
        # self.camera_params.magnification = camera_params.basler_fluor_camera_params.magnification

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        # self.p.v_zshim_current = .3

        self.p.t_tof = T_TOF_US * 1.e-6 # mot

        self.p.t_imaging_pulse = 5.e-6

        self.p.dummy = [1]*1000

        self.p.t_mot_load = T_MOTLOAD_S

        self.xvarnames = ['dummy']

        self.finish_build()

    @kernel
    def run(self):

        count = 0
        
        self.init_kernel(run_id=True)

        self.dds.second_imaging.set_dds(frequency=115.425e6,amplitude=0.188)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for _ in self.p.dummy:

            delay(1.0)
            
            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s)

            self.release()

            self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

            delay(10e-3*s)
            self.lightsheet.off()

            self.dds.second_imaging.on()
            delay(100.e-6*s)

            ### abs img
            delay(self.p.t_tof * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.dds.second_imaging.off()

            self.core.break_realtime()

            aprint(count)
            count += 1

            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        # self.ds.save_data(self)

        print("Done!")