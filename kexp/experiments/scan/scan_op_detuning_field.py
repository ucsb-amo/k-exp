from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

from kexp.util.artiq.async_print import aprint

import numpy as np

class scan_optical_pumping(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self,setup_camera=True,andor_imaging=False,absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan optical pumping detuning"

        ## Parameters

        self.p = self.params

        self.p.t_tweezer_hold = 30. * 1.e-3

        self.p.t_tof = 12000 * 1.e-6 # gm
        
        self.p.xvar_detune_optical_pumping_op = np.linspace(22.,28.,5) * 1.e6

        self.p.xvar_amp_optical_pumping_op = 2.5

        self.p.xvar_v_zshim_current_op = np.linspace(2,4,5)

        self.trig_ttl = self.get_device("ttl14")

        self.xvarnames = ['xvar_detune_optical_pumping_op','xvar_v_zshim_current_op']

        self.finish_build(shuffle=True)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_detune_optical_pumping_op:
            for xvar2 in self.p.xvar_v_zshim_current_op:

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)
                
                ### Turn off push beam and 2D MOT to stop the atomic beam ###
                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                self.gm_ramp(self.p.t_gmramp * s)
                self.trig_ttl.off()
                
                self.release()

                self.dds.optical_pumping.set_dds_gamma(delta=xvar1,
                                       amplitude=self.p.xvar_amp_optical_pumping_op)
                with parallel:
                    self.dds.optical_pumping.on()
                    self.set_magnet_current(v = xvar2)
                delay(t)
                
                ### abs img
                delay(self.p.t_tof * s)
                self.flash_repump()
                self.abs_image()
                # self.fl_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")    