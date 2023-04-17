from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.config import DDS_Calibration as ddscal
from kexp import Base

import numpy as np

class tof_gmramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        ## Parameters

        self.p = self.params

        self.p.t_mot_kill = 1
        self.p.t_mot_load = 3

        self.p.t_d2cmot = 5.e-3
        self.p.t_d1cmot = 7.e-3
        self.p.t_gm = 2.e-3
        self.p.t_gm_ramp = 2.e-3

        self.p.N_shots = 5
        self.p.N_repeats = 1
        # self.p.t_tof = np.linspace(1000,5000,self.p.N_shots) * 1.e-6
        # self.p.t_tof = np.linspace(2000,3500,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.linspace(10000,15000,self.p.N_shots) * 1.e-6
        self.p.t_tof = np.repeat(self.p.t_tof,self.p.N_repeats)

        self.xvarnames = ['t_tof']

        self.get_N_img()

        self.p.V_d2cmot_current = 1.5
        self.p.V_d1cmot_current = 2.0

        d = 8.

        #D1 CMOT
        self.p.detune_d1_c_d1cmot = 7.6
        self.p.amp_d1_c_d1cmot = 0.1880
        self.p.detune_d2_r_d1cmot = -4.2
        self.p.amp_d2_r_d1cmot = 0.079

        #GM
        self.p.detune_d1_c_gm = d
        self.p.amp_d1_c_gm = 0.13
        self.p.detune_d1_r_gm = d
        self.p.amp_d1_r_gm = 0.13

        div = 5
        p_frac_c = ddscal().dds_amplitude_to_power_fraction(self.p.amp_d1_c_gm)
        p_frac_r = ddscal().dds_amplitude_to_power_fraction(self.p.amp_d1_r_gm)
        amp_ramp_c = ddscal().power_fraction_to_dds_amplitude(np.linspace(p_frac_c,p_frac_c/div,100))
        amp_ramp_r = ddscal().power_fraction_to_dds_amplitude(np.linspace(p_frac_r,p_frac_r/div,100))
        self.p.amp_d1_c_gm_ramp = amp_ramp_c
        self.p.amp_d1_r_gm_ramp = amp_ramp_r

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for t_tof in self.p.t_tof:
            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)

            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d2(self.p.t_d2cmot * s)
            self.cmot_d1(self.p.t_d1cmot * s)

            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gm_ramp * s, self.p.amp_d1_c_gm_ramp, self.p.amp_d1_r_gm_ramp)
            
            self.release()
            
            ### abs img
            delay(t_tof * s)
            self.abs_image()

            self.core.break_realtime()

        # return to mot load state
        self.switch_all_dds(state=1)
        self.dds.imaging.off()

        self.core.break_realtime()
        self.switch_mot_magnet(1)

        self.zotino.write_dac(self.dac_ch_3Dmot_current_control,self.p.V_mot_current)
        self.zotino.load()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")