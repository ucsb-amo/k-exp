from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.analysis.image_processing.compute_ODs import *

from kexp.util.artiq.expt_params import ExptParams

from kexp.experiments.base.devices import devices
from kexp.experiments.base.mot import mot
from kexp.experiments.base.camera import camera
from kexp.experiments.base.image import image

import numpy as np
import pypylon.pylon as py

class TOF_MOT(EnvExperiment, devices, mot, camera, image):

    def build(self):

        ## Parameters

        self.p = ExptParams()

        self.p.t_mot_kill = 0.5
        
        self.p.t_mot_load = 0.25
        self.p.t_tof_list = np.linspace(0,1000,7) * 1.e-6
        self.p.N_img = 3 * len(self.p.t_tof_list)

        ## Device setup
        
        self.images = []
        self.images_timestamps = []

        self.prepare_devices()

        # print(dir(self.dds["push"]))

    @kernel
    def tof_expt(self,t_tof):
        self.kill_mot(self, self.p.t_mot_kill * s)
        self.load_2D_mot(self, self.p.t_2D_mot_load_delay * s)
        self.load_mot(self, self.p.t_mot_load * s, self.p)

        self.magnet_and_mot_off(self)

        delay(t_tof * s)
        self.trigger_camera(self, self.p)
        self.pulse_imaging_light(self, self.p.t_imaging_pulse * s)

        delay(self.p.t_light_only_image_delay * s)
        self.trigger_camera(self, self.p)
        self.pulse_imaging_light(self, self.p.t_imaging_pulse * s)

        delay(self.p.t_dark_image_delay * s)
        self.trigger_camera(self, self.p)
        delay(1*ms)

    @kernel
    def run(self):

        self.core.reset()
        # self.set_all_dds(state=0)
        self.core.break_realtime()

        x = self.dds
        print(x["imaging"])

        # camera.StartTriggeredGrab(self, self.p.N_img, self.images, self.images_timestamps)
        delay(0.25*s)
        self.core.break_realtime()
        
        for t in self.p.t_tof_list:
            # self.tof_expt(t)
            self.core.break_realtime()

        # return to mot load state
        # self.set_all_dds(state=1)
        # print(self.dds.get("imaging"))
        # self.dds.get("imaging").sw_off()

    def analyze(self):

        self.camera.close()
        
        _, summedODx, summedODy = analyze_and_save_absorption_images(self.images,self.images_timestamps,self)

        self.p.params_to_dataset(self)

        print("Done!")

        

        


            

        

