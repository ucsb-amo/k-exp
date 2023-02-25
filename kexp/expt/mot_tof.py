from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from wax.config.config_dds import defaults as default_dds
from wax.tools.util.ExptParams import ExptParams

from kexp.control.basler.BaslerUSB import BaslerUSB
from kexp.control.basler.TriggeredImage import TriggeredImage
from kexp.analysis.absorption.process_absorption_images import compute_OD

import numpy as np

class TOF_MOT(EnvExperiment):

    def read_dds_from_config(self):
        self.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        for dds0 in default_dds:
            dds0.dds_device = self.get_device(dds0.name())
            self.dds[dds0.urukul_idx][dds0.ch] = dds0

    def prepare(self):
        self.params = ExptParams()

        self.params.t_mot_kill_s = 1
        self.params.t_mot_load_s = 5
        self.params.t_2D_mot_load_delay_s = 2
        self.params.t_camera_trigger_us = 6
        self.params.t_imaging_pulse_us = 2
        self.params.t_light_only_image_delay_ms = 50
        self.params.t_dark_image_delay_ms = 50
        self.params.t_cam_exposure_time_us = 12

        self.params.t_tof_list_us = np.array([0])

        self.params.V_mot_current_V = 0.7

    def build(self):

        self.setattr_device("core")
        self.read_dds_from_config()
        
        self.zotino = self.get_device("zotino0")

        self.camera = BaslerUSB(ExposureTime=self.params.t_cam_exposure_time_us)

        self.dds_push = self.dds[0][0]
        self.dds_d2_2d_r = self.dds[0][1]
        self.dds_d2_2d_c = self.dds[0][2]
        self.dds_d2_3d_r = self.dds[0][3]
        self.dds_d2_3d_c = self.dds[1][0]
        # self.dds_d1_3d_r = self.dds[1][1]
        # self.dds_d1_3d_c = self.dds[1][2]
        self.dds_imaging = self.dds[1][1]

        self.ttl_camera = self.get_device("ttl4")
        # self.ttl_3d_magnet_toggle = self.get_device("ttl5")

    @kernel
    def kill_mot(self):
        with parallel:
            self.dds_push.dds_device.sw.off()
            self.dds_d2_3d_r.dds_device.sw.off()
            self.dds_d2_3d_c.dds_device.sw.off()
            # self.dds_d1_3d_r.dds_device.sw.off()
            # self.dds_d1_3d_c.dds_device.sw.off()
        
    @kernel
    def load_mot(self):
        self.dds_d2_2d_c.dds_device.sw.on()
        self.dds_d2_2d_r.dds_device.sw.on()
        delay(self.params.t_2D_mot_load_delay_s * s)
        with parallel:
            with sequential:
                self.zotino.write_dac(0,self.params.V_mot_current_V)
                self.zotino.load()
            self.dds_push.dds_device.sw.on()
            self.dds_d2_3d_r.dds_device.sw.on()
            self.dds_d2_3d_c.dds_device.sw.on()
            # self.dds_d1_3d_r.dds_device.sw.on()
            # self.dds_d1_3d_c.dds_device.sw.on()
        
    @kernel
    def magnet_and_mot_off(self):
        # magnets, 2D, 3D off
        with parallel:
            with sequential:
                self.zotino.write_dac(0,0.)
                self.zotino.load()
            self.dds_d2_2d_c.dds_device.sw.off()
            self.dds_d2_2d_r.dds_device.sw.off()
            self.dds_push.dds_device.sw.off()
            self.dds_d2_3d_c.dds_device.sw.off()
            self.dds_d2_3d_r.dds_device.sw.off()

    @kernel
    def trigger_camera(self):
        self.ttl_camera.pulse(self.params.t_camera_trigger_us * us)

    @kernel
    def pulse_imaging(self):
        self.dds_imaging.dds_device.sw.on()
        delay(self.params.t_imaging_pulse_us * us)
        self.dds_imaging.dds_device.sw.off()

    @kernel
    def tof_expt(self,t_tof_us):
        # self.kill_mot()
        # delay(self.params.t_mot_kill_s * s)

        self.load_mot()
        delay(self.params.t_mot_load_s * s)

        self.magnet_and_mot_off()

        delay(t_tof_us * us)
        with parallel:
            self.trigger_camera()
            self.pulse_imaging()

        delay(self.params.t_light_only_image_delay_ms * ms)
        with parallel:
            self.trigger_camera()
            self.pulse_imaging()

        delay(self.params.t_dark_image_delay_ms * ms)
        self.trigger_camera()

    @kernel
    def run(self):

        self.core.reset()
        [[dds.init_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]
        self.zotino.init()

        # [[dds.set_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]
        # self.core.break_realtime()
        # [[dds.dds_device.sw.off() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]

        for t_us in self.params.t_tof_list_us:
            self.tof_expt(t_us)

        # self.zotino.write_dac(0,self.params.V_mot_current_V)
        # self.zotino.load()

    def analyze(self):
        images = self.camera.grab_N_images(3*len(self.params.t_tof_list_us))
        ODs = compute_OD(images)

        self.set_dataset('img_atoms', images[0::3])
        self.set_dataset('img_light', images[1::3])
        self.set_dataset('img_dark', images[2::3])
        self.set_dataset('ODs', ODs)

        self.params.params_to_dataset(self)

        print("Done!")

        

        


            

        

