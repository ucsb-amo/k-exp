from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential

from kexp.analysis.image_processing.compute_ODs import *

from kexp.util.artiq.expt_params import ExptParams
from kexp.experiments.base import camera, devices, mot_load, image

import numpy as np
import pypylon.pylon as py

class TOF_MOT(EnvExperiment):

    def build(self):

        ## Parameters

        self.p = ExptParams()
        
        self.p.V_mot_current = 0.7 # 3.4A on 3D MOT coils
        self.p.t_mot_load = 0.25
        self.p.t_2D_mot_load_delay = 1
        self.p.t_camera_trigger = 2.e-6
        self.p.t_imaging_pulse = 5.e-6
        self.p.t_light_only_image_delay = 100.e-3
        self.p.t_dark_image_delay = 10.e-3
        self.p.t_tof_list = np.linspace(0,1000,7) * 1.e-6
        
        self.p.N_img = 3 * len(self.p.t_tof_list)

        ## Device setup
        
        self.images = []
        self.images_timestamps = []

        camera.prepare_camera(self, self.p)

    @kernel
    def tof_expt(self,t_tof):
        # self.kill_mot(self.p.t_mot_kill * s)
        mot_load.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        mot_load.load_mot(self.p.t_mot_load * s)

        mot_load.magnet_and_mot_off()

        delay(t_tof * s)
        image.trigger_camera()
        image.pulse_imaging_light(self.p.t_imaging_pulse * s)

        delay(self.p.t_light_only_image_delay * s)
        image.trigger_camera()
        image.pulse_imaging_light(self.p.t_imaging_pulse * s)

        delay(self.p.t_dark_image_delay * s)
        image.trigger_camera()

    @kernel
    def run(self):

        self.core.reset()
        devices.set_all_dds(self)
        self.core.break_realtime()

        camera.StartTriggeredGrab(self, self.p.N_img, self.images, self.images_timestamps)
        delay(0.25*s)
        self.core.break_realtime()
        
        for t in self.p.t_tof_list:
            self.tof_expt(t)
            self.core.break_realtime()

        # return to mot load state
        mot_load.load_2D_mot(0.1*s)
        mot_load.load_mot(0.1*s)

    def analyze(self):

        self.camera.close()
        
        _, summedODx, summedODy = analyze_and_save_absorption_images(self.images,self.images_timestamps,self)

        self.p.params_to_dataset(self)

        print("Done!")

        

        


            

        

