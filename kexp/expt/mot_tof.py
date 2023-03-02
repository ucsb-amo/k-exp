from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from wax.config.config_dds import defaults as default_dds
from wax.tools.util.ExptParams import ExptParams

from kexp.control.basler.BaslerUSB import BaslerUSB
from kexp.control.basler.TriggeredImage import TriggeredImage
from kexp.analysis.absorption.process_absorption_images import compute_OD

import numpy as np
import pypylon.pylon as py

class TOF_MOT(EnvExperiment):

    def read_dds_from_config(self):
        self.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        for dds0 in default_dds:
            dds0.dds_device = self.get_device(dds0.name())
            self.dds[dds0.urukul_idx][dds0.ch] = dds0

    @rpc(flags={"async"})
    def StartTriggeredGrab(self):
        self.camera.StartGrabbingMax(self.p.N_img, py.GrabStrategy_LatestImages)
        count = 0
        while self.camera.IsGrabbing():
            grab = self.camera.RetrieveResult(1000000,py.TimeoutHandling_ThrowException)
            if grab.GrabSucceeded():
                print(f'gotem (img {count+1}/{self.p.N_img})')
                img = grab.GetArray()
                img_t = grab.TimeStamp
                self.images.append(img)
                self.images_timestamps.append(img_t)
                count += 1
            if count >= self.p.N_img:
                break
        self.camera.StopGrabbing()
        self.camera.Close()

    def build(self):

        self.camera = BaslerUSB()

        ## Parameters
        self.p = ExptParams()
        self.p.V_mot_current_V = 0.7 # 3.4A on 3D MOT coils
        self.p.t_mot_kill_s = 0.2
        self.p.t_mot_load_s = 0.1
        self.p.t_2D_mot_load_delay_s = 0.1
        self.p.t_pretrigger_motload_s = 75.e-3
        self.p.t_camera_trigger_s = 2.e-6
        self.p.t_imaging_pulse_s = 10.e-6
        self.p.t_cam_overlap_time_s = 20.e-6
        self.p.t_imaging_delay_s = 5.e-6
        self.p.t_light_only_image_delay_s = 75.e-3
        self.p.t_dark_image_delay_s = 75.e-3
        self.p.t_tof_list_s = np.array([0,1000,2000,5000,10000]) * 1.e-6

        # account for rolling shutter
        t_row_delay_s = 9.e-6
        rows = self.camera.SensorHeight.GetValue()
        self.p.t_total_row_delay_s = t_row_delay_s * (rows - 1)
        self.p.t_cam_exposure_time_s = self.p.t_total_row_delay_s + self.p.t_cam_overlap_time_s
        self.camera.ExposureTime = self.p.t_cam_exposure_time_s * 1.e6

        self.p.t_exposure_delay_s = self.camera.BslExposureStartDelay.GetValue() * 1.e-6
        self.p.t_pretrigger_s = self.p.t_total_row_delay_s + self.p.t_exposure_delay_s
        
        self.p.N_img = 4 * len(self.p.t_tof_list_s)

        ## Device setup
        self.setattr_device("core")
        self.zotino = self.get_device("zotino0")
        self.read_dds_from_config()
        self.ttl_camera = self.get_device("ttl4")

        self.images = []
        self.images_timestamps = []

        self.dds_push = self.dds[0][0]
        self.dds_d2_2d_r = self.dds[0][1]
        self.dds_d2_2d_c = self.dds[0][2]
        self.dds_d2_3d_r = self.dds[0][3]
        self.dds_d2_3d_c = self.dds[1][0]
        # self.dds_d1_3d_r = self.dds[1][1] self.dds_d1_3d_c = self.dds[1][2]
        self.dds_imaging = self.dds[1][1]

        self.dac_ch_3Dmot_current_control = 0

    @kernel
    def set_and_turn_off_dds(self):
        for dds_sublist in self.dds:
            for dds in dds_sublist:
                dds.set_dds()
                dds.off()
        
    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds_push.dds_device.sw.off()
            self.dds_d2_3d_r.dds_device.sw.off()
            self.dds_d2_3d_c.dds_device.sw.off()
            # self.dds_d1_3d_r.dds_device.sw.off()
            # self.dds_d1_3d_c.dds_device.sw.off()
            delay(t)

    @kernel
    def load_2D_mot(self,t):
        self.dds_d2_2d_c.dds_device.sw.on()
        self.dds_d2_2d_r.dds_device.sw.on()
        delay(t)
        
    @kernel
    def load_mot(self,t):
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      self.p.V_mot_current_V)
                self.zotino.load()
            self.dds_push.dds_device.sw.on()
            self.dds_d2_3d_r.dds_device.sw.on()
            self.dds_d2_3d_c.dds_device.sw.on()
            # self.dds_d1_3d_r.dds_device.sw.on()
            # self.dds_d1_3d_c.dds_device.sw.on()
        delay(t)
        
    @kernel
    def magnet_and_mot_off(self):
        # magnets, 2D, 3D off
        with parallel:
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.)
                self.zotino.load()
            self.dds_d2_2d_c.dds_device.sw.off()
            self.dds_d2_2d_r.dds_device.sw.off()
            self.dds_push.dds_device.sw.off()
            self.dds_d2_3d_c.dds_device.sw.off()
            self.dds_d2_3d_r.dds_device.sw.off()

    @kernel
    def trigger_camera(self):
        '''
        Written to pretrigger camera such that all pixels of the camera will be
        exposing at the timeline position where this is called. Returns the
        timeline cursor to this position after pretrigger
        '''
        delay(-self.p.t_pretrigger_s * s)
        self.ttl_camera.pulse(self.p.t_camera_trigger_s * s)
        t_adv = self.p.t_pretrigger_s - self.p.t_camera_trigger_s
        delay(t_adv * s)

    @kernel
    def pulse_imaging(self,t):
        self.dds_imaging.dds_device.sw.on()
        delay(t)
        self.dds_imaging.dds_device.sw.off()

    @kernel
    def tof_expt(self,t_tof_s):
        self.kill_mot(self.p.t_mot_kill_s * s)
        self.load_2D_mot(self.p.t_2D_mot_load_delay_s * s)
        self.load_mot(self.p.t_mot_load_s * s)

        delay(-self.p.t_pretrigger_motload_s*s)
        self.trigger_camera()
        delay(self.p.t_pretrigger_motload_s*s)

        self.magnet_and_mot_off()

        delay(t_tof_s * s)
        self.trigger_camera()
        delay(self.p.t_imaging_delay_s * s)
        self.pulse_imaging(self.p.t_imaging_pulse_s * s)

        delay(self.p.t_light_only_image_delay_s * s)
        self.trigger_camera()
        delay(self.p.t_imaging_delay_s * s)
        self.pulse_imaging(self.p.t_imaging_pulse_s * s)

        delay(self.p.t_dark_image_delay_s * s)
        self.trigger_camera()

    @kernel
    def run(self):

        self.core.reset()
        [[dds.init_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]
        self.set_and_turn_off_dds()
        self.zotino.init()

        self.StartTriggeredGrab()
        delay(0.25*s)
        
        self.core.break_realtime()
        
        for t in self.p.t_tof_list_s:
            self.tof_expt(t)
            self.core.break_realtime()

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,
                                      self.p.V_mot_current_V)
        # delay(5*us)
        self.zotino.load()
        self.dds_imaging.dds_device.sw.off()

    def analyze(self):

        self.camera.Close()
        
        images = self.images

        # ODs = compute_OD(images)

        self.set_dataset('img_all',images)
        self.set_dataset('img_timestamps_ns',self.images_timestamps)

        # self.set_dataset('img_atoms', images[0::3])
        # self.set_dataset('img_light', images[1::3])
        # self.set_dataset('img_dark', images[2::3])
        # self.set_dataset('ODs', ODs)

        self.p.params_to_dataset(self)

        print("Done!")

        

        


            

        

