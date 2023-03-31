from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential
from kexp.analysis.base_analysis import atomdata
from kexp.analysis.tof import tof
from kexp.base.base import Base
import numpy as np

class cmot_tof(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3
        self.p.t_cmot = 5.e-6

        self.p.N_shots = 5
        self.p.N_repeats = 3
        self.p.t_tof = np.linspace(20,400,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        # rng = np.random.default_rng()
        # rng.shuffle(self.p.t_tof)

        self.p.N_img = 3 * len(self.p.t_tof)
        
        self.p.att_d2_r_cmot = 13.5
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        self.p.f_d2_r_mot = self.dds.d2_3d_r.detuning_to_frequency(-4.7)
        self.p.f_d2_c_mot = self.dds.d2_3d_c.detuning_to_frequency(-3.35)

        self.p.f_d2_r_cmot = self.dds.d2_3d_r.detuning_to_frequency(-3.7)

        self.p.f_d1_c_cmot = self.dds.d1_3d_c.detuning_to_frequency(6.5)

        self.p.V_cmot_current = 0.4
    
    @kernel
    def load_2D_mot(self,t):
        self.switch_d2_2d(1)
        delay(t)

    @kernel
    def load_mot(self,t):
        delay(-10*us)
        self.dds.d2_3d_r.set_dds(freq_MHz=self.p.f_d2_r_mot,
                                 att_dB=self.p.att_d2_r_mot)
        self.dds.d2_3d_c.set_dds(freq_MHz=self.p.f_d2_c_mot)
        delay(10*us)

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
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,self.p.V_cmot_current)
                self.zotino.load()
        delay(t)

    @kernel
    def kill_cmot(self):
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d2_2d(0)
            self.switch_d2_3d(0)
            self.dds.push.off()
            self.dds.d1_3d_c.off()
            
    @kernel
    def tof_expt(self,t_tof):
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        self.load_mot(self.p.t_mot_load * s)

        with parallel:
             self.dds.push.off()
             self.switch_d2_2d(0)
             self.cmot(self.p.t_cmot * s)
        
        self.kill_cmot()
        
        ### abs img
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
        
        self.kill_mot(self.p.t_mot_kill * s)
        for t in self.p.t_tof:
            self.tof_expt(t)
            self.core.break_realtime()

        # return to mot load state
        self.switch_all_dds(state=1)
        self.dds.imaging.off()
        self.core.break_realtime()
        self.switch_mot_magnet(1)

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,0.7)
        self.zotino.load()

    def analyze(self):

        self.camera.Close()
        
        data = atomdata(expt=self)

        # data.T_x = tof(data).compute_T_x(t=self.params.t_tof)

        data.save_data()

        print("Done!")

        

        


            

        

