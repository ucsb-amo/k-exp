from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
import kexp.analysis.image_processing.compute_ODs as compute_ODs
from kexp.base.base import Base
import numpy as np

class mot_tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 0.5
        self.p.t_mot_load = 0.25
        self.p.t_tof_list = np.linspace(0,1000,15) * 1.e-6
        self.p.N_img = 3 * len(self.p.t_tof_list)

    @kernel
    def load_mot(self,t):
        with parallel:
            self.switch_mot_magnet(1)
            self.switch_d2_3d(1)
            self.dds.push.on()
        delay(t)

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def load_2D_mot(self,t):
        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def release_mot(self):
        # magnets, 2D, 3D off
        self.switch_mot_magnet(0)
        delay(16*ns)
        with parallel:
            self.switch_d2_2d(0)
            self.switch_d2_3d(0)
            self.dds.push.off()

    @kernel
    def tof_expt(self,t_tof):
        self.kill_mot(self.p.t_mot_kill * s)
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        self.load_mot(self.p.t_mot_load * s)

        self.release_mot()

        delay(t_tof * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.p.t_imaging_pulse * s)

        delay(self.p.t_light_only_image_delay * s)
        self.trigger_camera()
        self.pulse_imaging_light(self.p.t_imaging_pulse * s)

        delay(self.p.t_dark_image_delay * s)
        self.trigger_camera()

    @kernel
    def run(self):

        self.core.reset()
        self.set_all_dds(state=0)
        self.core.break_realtime()

        self.StartTriggeredGrab(self.p.N_img)
        delay(self.p.t_grab_start_wait*s)
        self.core.break_realtime()
        
        for t in self.p.t_tof_list:
            self.tof_expt(t)
            self.core.break_realtime()

        # return to mot load state
        self.set_all_dds(state=1)
        print(self.dds.imaging.off())
        self.core.break_realtime()
        self.switch_mot_magnet(1)

    def analyze(self):

        self.camera.Close()
        
        compute_ODs.analyze_and_save_absorption_images(self)

        self.p.params_to_dataset(self)

        print("Done!")

        

        


            

        

