from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.base.base import Base
from kexp.analysis.base_analysis import atomdata
from kexp.analysis.tof import tof
import numpy as np

class gm_tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 0.5
        self.p.t_mot_load = 0.25
        self.p.t_gm = 10.e-6

        self.p.t_tof = np.linspace(20,500,4) * 1.e-6
        self.p.N_img = 3 * len(self.p.t_tof)
        
        # self.p.f_d1_r_gm = self.dds.d1_3d_r.detuning_to_frequency(3.5)
        # self.p.f_d1_c_gm = self.dds.d1_3d_c.detuning_to_frequency(4.5)

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
        self.switch_d2_2d(1)
        delay(t)

    @kernel
    def gm(self,t):
        with parallel:
            self.switch_mot_magnet(0)
            self.dds.d1_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d2_3d_r.off()
        delay(t)

    @kernel
    def kill_gm(self):
        with parallel:
            self.dds.d1_3d_r.off()
            self.dds.d1_3d_c.off()

    @kernel
    def tof_expt(self,t_tof):
        self.kill_mot(self.p.t_mot_kill * s)
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        self.load_mot(self.p.t_mot_load * s)

        with parallel:
            self.dds.push.off()
            self.switch_d2_2d(0)

        self.gm(self.p.t_gm * s)
        self.kill_gm()
        
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
        
        self.init_kernel()
        self.StartTriggeredGrab(self.p.N_img)
        delay(self.p.t_grab_start_wait*s)
        
        for t in self.p.t_tof:
            self.tof_expt(t)
            self.core.break_realtime()

        # return to mot load state
        self.switch_all_dds(state=1)
        self.dds.imaging.off()

    def analyze(self):

        self.camera.Close()
        
        data = atomdata(expt=self)

        data.T_x = tof(data).compute_T_x(t=self.params.t_tof)

        data.save_data()

        print("Done!")

        

        


            

        

