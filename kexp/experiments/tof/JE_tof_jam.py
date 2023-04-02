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

        self.p.t_cmot0 = 5.e-3
        self.p.t_cmot = 8.e-3
        self.p.t_gm = 1.5e-3

        self.p.N_shots = 5
        self.p.N_repeats = 3
        self.p.t_tof = np.linspace(20,800,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        # rng = np.random.default_rng()
        # rng.shuffle(self.p.t_tof)

        self.p.N_img = 3 * len(self.p.t_tof)
        
        #attentuation settings
        self.p.att_d2_r_cmot = 13.5
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        self.p.att_d1_c_gm = 9.7
        self.p.att_d1_r_gm = 11.5

        #MOT detunings
        self.p.f_d2_r_mot = self.dds.d2_3d_r.detuning_to_frequency(-4.7)
        self.p.f_d2_c_mot = self.dds.d2_3d_c.detuning_to_frequency(-3.3)

        #CMOT detunings
        self.p.f_d2_c_cmot = self.dds.d2_3d_c.detuning_to_frequency(-.9)
        self.p.f_d2_r_cmot = self.dds.d2_3d_r.detuning_to_frequency(-3.7)

        self.p.f_d1_c_cmot = self.dds.d1_3d_c.detuning_to_frequency(7)

        #GM Detunings
        gm_f = 7
        self.p.f_d1_c_gm = self.dds.d1_3d_c.detuning_to_frequency(gm_f)
        self.p.f_d1_r_gm = self.dds.d1_3d_r.detuning_to_frequency(gm_f)

        #MOT current settings
        self.p.V_cmot0_current = 1.5
        self.p.V_cmot_current = .4
    
    @kernel
    def load_2D_mot(self,t):
        with parallel:
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

    #compress MOT by changing D2 detunings and raising B field
    @kernel
    def cmot0(self,t):
        delay(-10*us)
        self.dds.d2_3d_r.set_dds(freq_MHz=self.p.f_d2_r_cmot)
        self.dds.d2_3d_c.set_dds(freq_MHz=self.p.f_d2_c_cmot, att_dB=self.p.att_d1_c_gm)
        delay(10*us)
        with parallel:
            self.switch_d2_3d(1)
            with sequential:
                self.zotino.write_dac(self.dac_ch_3Dmot_current_control,self.p.V_cmot0_current)
                self.zotino.load()
        delay(t)
    
    #hybrid compressed MOT with only D2 repump and D1 cooler, setting B field to lower value
    @kernel
    def cmot(self,t):
        delay(-10*us)
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

    #GM with only D1, turning B field off
    @kernel
    def gm(self,t):
        delay(-10*us)
        self.dds.d1_3d_r.set_dds(freq_MHz=self.p.f_d1_r_gm, att_dB=self.p.att_d1_r_gm)
        self.dds.d1_3d_c.set_dds(freq_MHz=self.p.f_d1_c_gm, att_dB=self.p.att_d1_c_gm)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d1_3d(1)
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def kill_cmot(self):
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d2_3d(0)
            self.switch_d1_3d(0)
            
    @kernel
    def tof_expt(self,t_tof):
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        self.load_mot(self.p.t_mot_load * s)

        self.dds.push.off()
        self.switch_d2_2d(0)

        self.cmot0(self.p.t_cmot0 * s)

        self.cmot(self.p.t_cmot * s)

        #self.gm(self.p.t_gm * s)
        
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
        
        data = atomdata('t_tof',expt=self)

        data.save_data()

        print("Done!")

        

        


            

        

