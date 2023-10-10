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
        self.p.t_tof = 7000 * 1.e-6

        #Ramp params

        self.p.N_shots = 5
        self.p.N_repeats = [1,1]

        self.p.xvar_pfrac_gmramp_c_end = np.linspace(0.6,1.,5)
        self.p.xvar_pfrac_gmramp_r_end = np.linspace(0.05,.75,5)

        self.p.c_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_c_end), self.p.n_gmramp_steps))
        self.p.r_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_r_end), self.p.n_gmramp_steps))

        cal = DDS_VVA_Calibration()

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_c_end)):
            self.p.c_ramp[idx1][:] = np.linspace(self.p.pfrac_c_gmramp_start, self.p.xvar_pfrac_gmramp_c_end[idx1], self.p.n_gmramp_steps)
        for idx1 in range(len(self.p.xvar_pfrac_gmramp_r_end)):
            self.p.r_ramp[idx1][:] = np.linspace(self.p.pfrac_r_gmramp_start, self.p.xvar_pfrac_gmramp_r_end[idx1], self.p.n_gmramp_steps)

        self.c_ramp_vva = cal.power_fraction_to_vva(self.p.c_ramp)
        self.r_ramp_vva = cal.power_fraction_to_vva(self.p.r_ramp)

        # self.keys = np.empty((len(self.p.xvar_pfrac_gmramp_c_end),len(self.p.xvar_pfrac_gmramp_r_end)),dtype=str)
        # for idx1 in range(len(self.p.xvar_pfrac_gmramp_c_end)):
        #     for idx2 in range(len(self.p.xvar_pfrac_gmramp_r_end)):
        #         # unique string to label each ramp
        #         # must be done outside kernel
        #         self.p.keys[idx1][idx2] = str(idx1) + str(idx2)

        self.xvarnames = ['xvar_pfrac_gmramp_c_end','xvar_pfrac_gmramp_r_end']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_c_end)):
            for idx2 in range(len(self.p.xvar_pfrac_gmramp_r_end)):

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                # self.cmot_d2(self.p.t_d2cmot * s)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)
                
                with parallel:
                    self.ttl_magnets.off()
                    self.switch_d1_3d(1)
                    self.switch_d2_3d(0)

                dt_gmramp = self.p.t_gmramp / self.p.n_gmramp_steps
                for n in range(self.p.n_gmramp_steps):
                    self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp_vva[idx1][n])
                    delay_mu(self.params.t_rtio_mu)
                    self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp_vva[idx2][n])
                    delay(dt_gmramp)

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
