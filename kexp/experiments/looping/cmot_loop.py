from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.analysis.base_analysis import atomdata
from kexp.analysis.tof import tof
from kexp.base.base import Base
import numpy as np

class cmot_loop(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_2D_mot_load_delay = 5
        self.p.t_mot_load = 10
        self.p.t_cmot = 1000.e-6

        self.p.N = 1
        
        self.p.att_d2_r_cmot = 13.50
        self.p.f_d2_r_cmot = self.dds.d2_3d_r.detuning_to_frequency(-1.7)
        self.p.f_d1_c_cmot = self.dds.d1_3d_c.detuning_to_frequency(4.5)

    @kernel
    def load_mot(self,t):
        with parallel:
            self.switch_mot_magnet(1)
            self.switch_d2_3d(1)
            self.dds.push.on()
        delay(t)

    @kernel
    def load_2D_mot(self,t):
        self.switch_d2_2d(1)
        delay(t)

    @kernel
    def cmot(self,t):
        delay(-10*us)
        with parallel:
            self.dds.d2_3d_r.set_dds(freq_MHz=self.p.f_d2_r_cmot,
                                     att_dB=self.p.att_d2_r_cmot)
            self.dds.d1_3d_c.set_dds(freq_MHz=self.p.f_d1_c_cmot)
        delay(10*us)
        with parallel:
            self.dds.d2_3d_r.on()
            self.dds.d1_3d_c.on()
            self.dds.d2_3d_c.off()
            self.dds.d1_3d_r.off()
        delay(t)

    @kernel
    def kill_cmot(self):
        with parallel:
            self.switch_mot_magnet(0)
            self.dds.d2_3d_r.off()
            self.dds.d1_3d_c.off()

    @kernel
    def run(self):
        
        self.init_kernel()
        
        for _ in range(self.p.N):

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
            self.load_mot(self.p.t_mot_load * s)

            with parallel:
                self.dds.push.off()
                self.switch_d2_2d(0)
                self.cmot(self.p.t_cmot * s)

    def analyze(self):

        print("Done!")

        

        


            

        

