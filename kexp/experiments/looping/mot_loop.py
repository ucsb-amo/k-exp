from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.analysis.base_analysis import atomdata
from kexp.analysis.tof import tof
from kexp.base.base import Base
import numpy as np

class mot_loop(EnvExperiment, Base):

    def build(self):
        Base.__init__(self,setup_camera=False)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_2D_mot_load_delay = 5
        self.p.t_mot_load = 10
        self.p.t_cmot = 1000.e-6

        self.p.N = 1

        self.p.f_d2_r_mot = self.dds.d2_3d_r.detuning_to_frequency(-4.7)
        
        self.p.att_d2_r_cmot = 13.50
        self.p.f_d2_r_cmot = self.dds.d2_3d_r.detuning_to_frequency(-3.7)

    @kernel
    def load_2D_mot(self,t):
        self.switch_d2_2d(1)
        delay(t)

    @kernel
    def run(self):
        
        self.init_kernel()
        self.switch_mot_magnet(1)
        
        for _ in range(self.p.N):

            self.dds.d2_3d_r.set_dds(freq_MHz=self.p.f_d2_r_mot)

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
            with parallel:
                self.switch_d2_3d(1)
                self.dds.push.on()
            delay(5*s)
            # self.dds.d2_3d_r.set_dds(freq_MHz=101.32)
            self.dds.d2_3d_r.set_dds(freq_MHz=self.p.f_d2_r_cmot, att_dB=self.p.att_d2_r_cmot)
            delay(5*s)

    def analyze(self):

        print("Done!")

        

        


            

        

