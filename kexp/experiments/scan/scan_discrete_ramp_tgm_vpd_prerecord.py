from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np
from kexp.config.dds_calibration import DDS_VVA_Calibration

class scan_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "gm tof, vary discrete ramp params"

        ## Parameters

        self.p = self.params

        #Ramp params

        self.p.N_repeats = [1,1]
        self.p.xvar_pfrac_gmramp_end = np.linspace(0.3,0.7,6)

        self.c_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_end), self.p.n_gmramp_steps))
        self.r_ramp = np.zeros((len(self.p.xvar_pfrac_gmramp_end), self.p.n_gmramp_steps))

        self.p.t_tof = 12000 * 1.e-6

        self.p.xvar_t_gmramp = np.linspace(3.,10.,6) * 1.e-3

        # self.p.xvar_t_tof = np.linspace(11.,15.,6) * 1.e-3
        # self.p.xvar_t_gmramp = np.linspace(11.,15.,6) * 1.e-3

        cal = DDS_VVA_Calibration()

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_end)):
                self.c_ramp[idx1][:] = np.linspace(self.p.pfrac_c_gmramp_start, self.p.xvar_pfrac_gmramp_end[idx1], self.p.n_gmramp_steps)
                self.r_ramp[idx1][:] = np.linspace(self.p.pfrac_r_gmramp_start, self.p.xvar_pfrac_gmramp_end[idx1], self.p.n_gmramp_steps)

        self.c_ramp_vva = cal.power_fraction_to_vva(self.c_ramp)
        self.r_ramp_vva = cal.power_fraction_to_vva(self.r_ramp)

        self.keys = np.empty((len(self.p.xvar_pfrac_gmramp_end),len(self.p.xvar_t_gmramp)),dtype=str)
        for idx1 in range(len(self.p.xvar_pfrac_gmramp_end)):
            for idx2 in range(len(self.p.xvar_t_gmramp)):
                # unique string to label each ramp
                # must be done outside kernel
                self.keys[idx1][idx2] = str(idx1) + str(idx2)

        self.xvarnames = ['xvar_pfrac_gmramp_end','xvar_t_gmramp']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build(shuffle=False)

    @kernel
    def record_ramps(self):
        for idx1 in range(len(self.p.xvar_pfrac_gmramp_end)):
            for idx2 in range(len(self.p.xvar_t_gmramp)):
                # retrieve key that labels this recorded ramp
                key = self.keys[idx1][idx2]
                t_gmramp = self.p.xvar_t_gmramp[idx2]
                dt_gmramp = t_gmramp / self.p.n_gmramp_steps
                # record the ramp
                with self.core_dma.record(key):
                    for n in range(self.p.n_gmramp_steps):
                        self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp_vva[idx1][n])
                        delay_mu(self.params.t_rtio_mu)
                        self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp_vva[idx1][n])
                        delay(dt_gmramp)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.record_ramps()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for idx1 in range(len(self.p.xvar_pfrac_gmramp_end)):
            for idx2 in range(len(self.p.xvar_t_gmramp)):

                # retrieve the ramp for this run
                key = self.keys[idx1][idx2]
                ramp_handle = self.core_dma.get_handle(key)
                self.core.break_realtime()

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                with parallel:
                    self.ttl_magnets.off()
                    self.switch_d1_3d(1)
                    self.switch_d2_3d(0)

                # play back the ramp
                self.core_dma.playback_handle(ramp_handle)

                self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
