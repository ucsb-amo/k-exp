from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration

class scan_gm_params(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "GM v_pd_d1_c_gm vs v_pd_r"
        # self.run_info._run_description = "GM detune_c vs detune_r"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 15000.e-6

        self.p.xvar_t_gm = np.linspace(.5,12.,6) * 1.e-3

        #GM Detunings
        self.p.xvar_detune_gm = np.linspace(5.,9.0,5)

        # self.p.xvar_detune_d1_c_gm = np.linspace(5.5,9.0,5)
        # self.p.xvar_detune_d1_r_gm = np.linspace(5.5,9.0,5)

        # self.p.xvar_pfrac_d1_c_gm = np.linspace(0.6,1.0,5)
        # self.p.xvar_pfrac_d1_r_gm = np.linspace(0.6,1.0,6)

        cal = self.dds.dds_vva_calibration

        # self.p.xvar_v_pd_c_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_c_gm)
        # self.p.xvar_v_pd_r_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_r_gm)
        
        

        self.xvarnames = ['xvar_t_gm','xvar_detune_gm']
        # self.xvarnames = ['xvar_detune_d1_c_gm', 'xvar_detune_d1_r_gm']
        # self.xvarnames = ['xvar_pfrac_d1_c_gm', 'xvar_pfrac_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_v_pd_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_t_gm']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_t_gm:
            for xvar2 in self.p.xvar_detune_gm:
                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                # self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(xvar1* s, detune_d1=xvar2)

                self.gm_ramp(t_gmramp=self.p.t_gmramp)
                self.trig_ttl.off()

                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
