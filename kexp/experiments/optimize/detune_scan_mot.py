from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.analysis.base_analysis import atomdata
from kexp.base.base import Base
import numpy as np

class detune_scan_mot(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2_cmot = 5.e-3
        self.p.t_hybrid_cmot = 7.e-3
        self.p.t_gm = 1.5e-3

        self.p.N_shots = 8
        self.p.N_repeats = 1

        self.p.t_tof = 500.e-6

        #MOT detunings

        # self.p.detune_d2_c_mot = -3.3
        # self.p.detune_d2_r_mot = -4.7

        self.p.detune_d2_c_mot = np.linspace(0,-6,self.p.N_shots)
        self.p.att_d2_c_mot = self.dds.d2_3d_c.att_dB
        self.p.detune_d2_r_mot = np.linspace(0,-6,self.p.N_shots)
        self.p.att_d2_r_mot = self.dds.d2_3d_r.att_dB

        #MOT current settings
        self.p.V_cmot0_current = 1.5
        self.p.V_cmot_current = .4

        self.xvarnames = ['detune_d2_c_mot','detune_d2_r_mot']

        self.get_N_img()
    
    @kernel
    def load_2D_mot(self,t):
        with parallel:
            self.switch_d2_2d(1)
        delay(t)

    @kernel
    def load_mot(self,t,delta_c,delta_r):
        delay(-10*us)
        self.dds.d2_3d_c.set_dds_gamma(delta=delta_c,
                                 att_dB=self.p.att_d2_c_mot)
        delay_mu(self.p.t_rtio_mu)
        self.dds.d2_3d_r.set_dds_gamma(delta=delta_r,
                                 att_dB=self.p.att_d2_r_mot)
        delay(10*us)
        with parallel:
            self.switch_mot_magnet(1)
            self.switch_d2_3d(1)
            delay_mu(self.p.t_rtio_mu)
            self.dds.push.on()
        delay(t)

    @kernel
    def kill_mot(self,t):
        with parallel:
            self.dds.push.off()
            self.switch_d2_3d(0)
        delay(t)

    @kernel
    def kill_trap(self):
        with parallel:
            self.switch_mot_magnet(0)
            self.switch_d2_3d(0)
            self.switch_d1_3d(0)

    @kernel
    def abs_image(self):
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

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for delta_c in self.p.detune_d2_c_mot:
            for delta_r in self.p.detune_d2_r_mot:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.load_mot(self.p.t_mot_load * s, delta_c, delta_r)

                self.dds.push.off()
                self.switch_d2_2d(0)
                
                self.kill_trap()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

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
        
        self.ds.save_data(self)

        print("Done!")

        

        


            

        

