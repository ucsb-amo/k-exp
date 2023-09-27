from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class tof_scan_gm(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "cmot tof, vary cmot time"

        ## Parameters

        self.p = self.params

        self.p.t_tof = np.linspace(1200.,1800.,2) * 1.e-6

        self.p.detune_d2_c_mot_start = self.p.detune_d2_c_mot
        self.p.detune_d2_r_mot_start = self.p.detune_d2_r_mot

        self.p.detune_d2_mot_change = np.linspace(0.,4.,3)

        self.p.t_ramp = 1.e-3

        idx = 0
        for delta in self.p.detune_d2_mot_change:

            deltas = np.linspace(0,delta,100)

            detunings_c = self.p.detune_d2_c_mot_start + deltas
            d2_c_f_list = [self.dds.d2_3d_c.detuning_to_frequency(d) for d in detunings_c]

            detunings_r = self.p.detune_d2_r_mot_start + deltas
            d2_r_f_list = [self.dds.d2_3d_r.detuning_to_frequency(d) for d in detunings_r]

            self.dds.set_frequency_ramp_profile(self.dds.d2_3d_c,
                                                freq_list=d2_c_f_list,
                                                t_ramp=self.p.t_ramp,dds_mgr_idx=idx)
            self.dds.set_frequency_ramp_profile(self.dds.d2_3d_r,
                                                freq_list=d2_r_f_list,
                                                t_ramp=self.p.t_ramp,dds_mgr_idx=idx)
            
            idx += 1

        self.xvarnames = ['detune_d2_mot_change','t_tof']
        self.p.N_repeats = [1,1]

        self.trig_ttl2 = self.get_device("ttl8")

        self.finish_build(shuffle=True)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx in range(len(self.p.detune_d2_mot_change)):
            for t_tof in self.p.t_tof:

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                # get it ready
                
                self.mot(self.p.t_mot_load * s)

                self.dds.load_profile(dds_mgr_idx=idx)
                self.dds.enable(dds_mgr_idx=idx)
                
                # go go gadget ramp
                self.dds.commit_enable(dds_mgr_idx=idx)
                self.dds.disable()
                delay(self.p.t_ramp)

                self.dds.commit_disable(dds_mgr_idx=idx)

                self.dds.push.off()
                self.switch_d2_2d(0)

                # self.cmot_d1(self.p.t_d1cmot)

                # self.cmot_d2(self.p.t_d2cmot * s)

                # self.trig_ttl2.on()
                # self.cmot_d1_ramp(dt=dt,v_current=cmot_values)
                # self.trig_ttl2.off()

                # self.trig_ttl.on()
                # self.gm(self.p.t_gm * s)

                # self.gm_ramp(t_gmramp=self.p.t_gmramp)
                # self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
