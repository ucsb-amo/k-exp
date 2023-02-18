from artiq.experiment import *
from artiq.experiment import delay, parallel
from wax.devices.DDS import DDS
from wax.config.config_dds import defaults as default_dds

from kexp.control.basler.BaslerUSB import BaslerUSB
from kexp.analysis.absorption.process_absorption_images import compute_OD

class MOT_TOF(EnvExperiment):

    def read_dds_from_config(self):
        N_uru = 3
        N_ch = 4
        self.dds = [[0,0,0,0],[0,0,0,0],[0,0,0,0]]
        for uidx in range(N_uru):
            for ch in range(N_ch):
                dds0 = default_dds[uidx*N_ch + ch]
                dds0.dds_device = self.get_device(dds0.name())
                self.dds[dds0.urukul_idx][dds0.ch] = dds0

    def prepare(self):
        self.t_mot_kill = 1*s
        self.t_mot_load = 5*s
        self.t_magnet_off_delay = 2*ms
        self.t_camera_trigger = 10*us
        self.t_imaging_pulse = 5*us
        self.t_light_only_image_delay = 100*us

        self.t_tof_list = [500,1000,1500]

    def build(self):

        self.setattr_argument("core")
        self.read_dds_from_config()

        self.camera = BaslerUSB()

        self.dds_push = self.dds[0][0]
        self.dds_d2_2d_r = self.dds[0][1]
        self.dds_d2_2d_c = self.dds[0][2]
        self.dds_d2_3d_r = self.dds[0][3]
        self.dds_d2_3d_c = self.dds[1][0]
        # self.dds_d1_3d_r = self.dds[1][1]
        # self.dds_d1_3d_c = self.dds[1][2]
        self.dds_imaging = self.dds[1][3]

        self.ttl_camera = self.get_device("ttl4")
        self.ttl_3d_magnet_toggle = self.get_device("ttl5")

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
        with parallel:
            self.dds_push.dds_device.sw.on()
            self.dds_d2_3d_r.dds_device.sw.on()
            self.dds_d2_3d_c.dds_device.sw.on()
            # self.dds_d1_3d_r.dds_device.sw.on()
            # self.dds_d1_3d_c.dds_device.sw.on()
        
    @kernel
    def magnet_and_mot_off(self):
        # magnets, 2D, 3D off
        with parallel:
            self.ttl_3d_magnet_toggle.on()
            self.dds_d2_2d_c.dds_device.sw.off()
            self.dds_d2_2d_r.dds_device.sw.off()
            self.dds_push.dds_device.sw.off()
            self.dds_d2_3d_c.dds_device.sw.off()
            self.dds_d2_3d_r.dds_device.sw.off()

    @kernel
    def trigger_camera(self):
        self.ttl_camera.pulse(self.t_camera_trigger)

    @kernel
    def pulse_imaging(self):
        self.dds_imaging.dds_device.sw.on()
        delay(self.t_imaging_pulse)
        self.dds_imaging.dds_device.sw.off()

    @kernel
    def tof_expt(self,t_tof):
        self.kill_mot()
        delay(self.t_mot_kill)

        self.load_mot()
        delay(self.t_mot_load)

        self.magnet_and_mot_off()

        delay(t_tof * us)
        self.trigger_camera()
        self.pulse_imaging()

        delay(self.t_light_only_image_delay)
        self.trigger_camera()
        self.pulse_imaging()

        delay(self.t_delay)

        self.trigger_camera()

    @kernel
    def run(self):

        self.core.reset()
        [[dds.init_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]
        [[dds.set_dds() for dds in dds_on_this_uru] for dds_on_this_uru in self.dds]

        for t in self.t_tof_list:
            self.tof_expt(t)

    def analyze(self):
        images = self.camera.grab_N_images(3*len(self.t_tof_list))
        ODs = compute_OD(images)

        



            

        

