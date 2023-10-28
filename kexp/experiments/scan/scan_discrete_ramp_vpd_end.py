from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration

class scan_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof, vary discrete ramp params"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000.,7000.,3) * 1.e-6
        self.p.t_tof = 13000 * 1.e-6

        self.p.t_gmramp = 4.5e-3

        #Ramp params

        self.p.N_shots = 5
        self.p.N_repeats = [1,1]

        self.p.pfrac_c_gmramp_start = self.p.pfrac_d1_c_gm
        self.p.pfrac_r_gmramp_start = self.p.pfrac_d1_r_gm

        # self.p.pfrac_c_gmramp_start = 1.
        # self.p.pfrac_r_gmramp_start = 1.

        self.p.xvar_pfrac_gmramp_c_end = np.linspace(0.1,0.55,7)
        self.p.xvar_pfrac_gmramp_r_end = np.linspace(0.02,0.3,7)

        self.p.c_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_c_end), self.p.n_gmramp_steps))
        self.p.r_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_r_end), self.p.n_gmramp_steps))

        cal = DDS_VVA_Calibration()

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_c_end)):
            self.p.c_ramp[idx1][:] = np.linspace(self.p.pfrac_c_gmramp_start, self.p.xvar_pfrac_gmramp_c_end[idx1], self.p.n_gmramp_steps)
        for idx1 in range(len(self.p.xvar_pfrac_gmramp_r_end)):
            self.p.r_ramp[idx1][:] = np.linspace(self.p.pfrac_r_gmramp_start, self.p.xvar_pfrac_gmramp_r_end[idx1], self.p.n_gmramp_steps)

        self.p.c_ramp_vva = cal.power_fraction_to_vva(self.p.c_ramp)
        self.p.r_ramp_vva = cal.power_fraction_to_vva(self.p.r_ramp)

        # c_ramp_start = 5.
        # r_ramp_start = 5.

        # self.p.xvar_c_ramp_end = np.linspace(.1,3.,5)
        # self.p.xvar_r_ramp_end = np.linspace(.1,3.,5)

        # self.p.c_ramp = np.zeros((len(self.p.xvar_c_ramp_end), self.p.n_gmramp_steps))
        # self.p.r_ramp = np.zeros((len(self.p.xvar_r_ramp_end), self.p.n_gmramp_steps))

        # for i in range(len(self.p.xvar_c_ramp_end)):
        #     self.p.c_ramp[i][:] = np.linspace(c_ramp_start, self.p.xvar_c_ramp_end[i], self.p.n_gmramp_steps)
        # for i in range(len(self.p.xvar_r_ramp_end)):
        #     self.p.r_ramp[i][:] = np.linspace(r_ramp_start, self.p.xvar_r_ramp_end[i], self.p.n_gmramp_steps)

        self.xvarnames = ['xvar_pfrac_gmramp_c_end','xvar_pfrac_gmramp_r_end']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_c_end)):
            for idx2 in range(len(self.p.xvar_pfrac_gmramp_r_end)):

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()

                # self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                dt_gmramp = self.p.t_gmramp / self.p.n_gmramp_steps
                for n in range(self.p.n_gmramp_steps):
                    self.dds.d1_3d_c.set_dds_gamma(v_pd=self.p.c_ramp_vva[idx1][n])
                    delay_mu(self.params.t_rtio_mu)
                    self.dds.d1_3d_r.set_dds_gamma(v_pd=self.p.r_ramp_vva[idx2][n])
                    delay(dt_gmramp)

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
