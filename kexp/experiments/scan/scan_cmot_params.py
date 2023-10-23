from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.config.dds_calibration import DDS_VVA_Calibration

class scan_cmot_params(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "cmot D2 r detuning vs d2 r amp"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 6000.e-6

        # self.p.xvar_detune_d2_c_d2cmot = np.linspace(0.,-1.7,5)
        # self.p.xvar_detune_d2_r_d2cmot = np.linspace(0.,-3.0,5)

        # self.p.xvar_v_d2cmot_current = np.linspace(0.5,1.7,6)

        # self.p.xvar_t_d1cmot = np.linspace(2.,30.0,6) * 1.e-3

        # self.p.xvar_detune_d2_r_d1cmot = np.linspace(-3.75,-3.0,5)

        # self.p.xvar_amp_d2_r_d1cmot = np.linspace(0.03,.05,5)

        self.p.xvar_detune_d1_c_d1cmot = np.linspace(5.,10.,5)

        self.p.xvar_pfrac_d1_c_d1cmot = np.linspace(0.5,.8,5)
        cal = self.dds.dds_vva_calibration
        self.p.xvar_v_pd_d1_c_d1cmot = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_c_d1cmot)

        # self.p.xvar_amp_c = np.repeat(self.p.xvar_amp_c,3)
        # self.p.xvar_amp_r = np.repeat(self.p.xvar_amp_r,3)

        # self.p.xvar_v_d1cmot_current = np.linspace(0.65,1.2,5)

        self.trig_ttl = self.get_device("ttl14")

        # self.xvarnames = ['xvar_detune_d1_c_d1cmot', 'xvar_detune_d2_r_d1cmot']
        # self.xvarnames = ['xvar_detune_d1_c_d1cmot', 'xvar_detune_d2_r_d1cmot']
        # self.xvarnames = ['xvar_v_pd_d1_c_d1cmot', 'xvar_amp_d2_r_d1cmot']
        # self.xvarnames = ['xvar_detune_d2_r_d1cmot', 'xvar_amp_d2_r_d1cmot']
        self.xvarnames = ['xvar_detune_d1_c_d1cmot', 'xvar_pfrac_d1_c_d1cmot']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar_0 in self.p.xvar_detune_d1_c_d1cmot:
            for xvar_1 in self.p.xvar_v_pd_d1_c_d1cmot:

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                # self.switch_d2_2d(0)

                # self.cmot_d2(self.p.t_d2cmot * s)

                # self.cmot_d1(self.p.t_d1cmot * s, detune_d2_r=xvar_0, amp_d2_r=xvar_1)
                self.trig_ttl.on()
                self.cmot_d1(self.p.t_d1cmot * s, detune_d1_c=xvar_0, v_pd_d1_c=xvar_1)
                self.trig_ttl.off()

                # self.trig_ttl.on()
                # self.gm(self.p.t_gm * s)

                # self.gm_ramp(self.p.t_gm_ramp)
                # self.trig_ttl.off()

                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()
                
                delay(self.p.t_recover)

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        # self.p.detune_gm = self.p.xvar_detune_gm
        # self.p.amp_d1_c_gm = self.p.xvar_amp_c

        # self.p.detune_d2_r_d1cmot = self.p.xvar_detune_d2_r_d1cmot
        # self.p.amp_d2_r_d1cmot = self.p.xvar_amp_d2_r_d1cmot

        # self.p.detune_d2_c_d2cmot = self.p.xvar_detune_d2_c_d2cmot
        # self.p.detune_d2_r_d2cmot = self.p.xvar_detune_d2_r_d2cmot
        
        # self.p.detune_d1_c_d1cmot = self.p.xvar_detune_d1_c_d1cmot
        # self.p.v_pd_d1_c_d1cmot = self.p.xvar_v_pd_d1_c_d1cmot

        # self.p.v_d2cmot_current = self.p.xvar_v_d2cmot_current
        # self.p.t_d2cmot = self.p.xvar_t_d2cmot

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")