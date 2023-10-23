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

        # self.p.v_zshim_current = .3

        # self.p.detune_gm = 9.2
        # self.p.t_gm = 3.e-3

        # self.p.t_tof = np.linspace(3000,8000,5) * 1.e-6
        self.p.t_tof = 10000.e-6

        self.p.xvar_t_gm = np.linspace(1.,9.,5) * 1.e-3
        self.p.xvar_detune_gm = np.linspace(6.,11.0,5)

        # self.p.xvar_detune_d1_c_gm = np.linspace(7.,12.0,5)
        # self.p.xvar_detune_d1_r_gm = np.linspace(7.,12.0,5)

        self.p.xvar_pfrac_d1_c_gm = np.linspace(0.2,.7,8)
        self.p.xvar_pfrac_d1_r_gm = np.linspace(0.2,.7,8)

        cal = self.dds.dds_vva_calibration

        self.p.xvar_v_pd_c_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_c_gm)
        self.p.xvar_v_pd_r_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_r_gm)

        self.xvarnames = ['xvar_pfrac_d1_c_gm','xvar_pfrac_d1_r_gm']
        # self.xvarnames = ['xvar_detune_d1_c_gm', 'xvar_detune_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_pfrac_d1_r_gm']
        # self.xvarnames = ['xvar_detune_gm', 'xvar_t_gm']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_v_pd_c_gm:
            for xvar2 in self.p.xvar_v_pd_r_gm:

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()

                # self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s, v_pd_d1_c=xvar1, v_pd_d1_r=xvar2)
                # self.gm(self.p.t_gm * s, detune_d1_c=xvar1, detune_d1_r=xvar2)

                # self.gm_ramp(t_gmramp=self.p.t_gmramp)
                self.trig_ttl.off()

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

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
