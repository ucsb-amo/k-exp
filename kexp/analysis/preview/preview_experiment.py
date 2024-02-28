from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.util.artiq.async_print import aprint
import msvcrt

import numpy as np

T_TOF_US = 40
T_MOTLOAD_S = 1.0

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self, camera_select="xy_basler")
        
        # comment in/out to switch to abs imaging on x-axis
        # self.camera_params.serial_no = camera_params.basler_fluor_camera_params.serial_no
        # self.camera_params.magnification = camera_params.basler_fluor_camera_params.magnification

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.amp_imaging_abs = 0.25

        # self.p.v_zshim_current = .3

        self.p.t_tof = T_TOF_US * 1.e-6 # mot

        self.p.t_imaging_pulse = 5.e-6

        self.p.dummy = [1]*1000

        self.p.t_mot_load = T_MOTLOAD_S

        self.xvarnames = ['dummy']

        # self.p.t_magnet_off_pretrigger = 1.e-3
        self.p.t_gm = 5.e-3

        self.finish_build()

        print('hi')

    @rpc(flags={"async"})
    def watch_for_keypress(self):
        self.stop_flag = False
        while True:
            if msvcrt.kbhit():
                self.stop_flag = True
                break

    @kernel
    def run(self):

        count = 0
        
        self.init_kernel(run_id=True)

        self.watch_for_keypress()
        delay(1*s)

        # # self.dds.second_imaging.set_dds(frequency=115.425e6,amplitude=0.188)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for _ in self.p.dummy:

            if self.stop_flag:

                delay(.5)
                
                self.mot(self.p.t_mot_load * s)
                self.dds.push.off()
                self.cmot_d1(self.p.t_d1cmot * s)
                self.gm(self.p.t_gm * s)
                # self.gm_ramp(self.p.t_gmramp * s)

                self.release()

                # self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)
                # self.tweezer_1064_ramp(t_tweezer_1064_ramp=10.e-3)
                # delay(.5e-3*s)
                # self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampup)
                # self.lightsheet.off()
                # delay(1.2e-3*s)

                self.dds.mot_killer.on()
                # delay(200.e-6*s)
                
                # self.dds.tweezer_aod.off()

                ### abs img
                delay(self.p.t_tof * s)
                # self.fl_image()
                self.flash_repump()
                self.abs_image()

                self.dds.mot_killer.off()

                self.core.break_realtime()

                aprint(count)
                count += 1

                delay(self.p.t_recover)

            else:
                self.core.reset()
                break

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        # self.ds.save_data(self)

        print("Done!")