from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp.base.base import Base
import numpy as np

class scan_discrete_ramp(EnvExperiment, Base):

    def build(self):
        Base.__init__(self)

        self.run_info._run_description = "mot tof, vary discrete ramp params"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(3000.,7000.,3) * 1.e-6
        self.p.t_tof = 5000 * 1.e-6

        #Ramp params
        self.p.xvar_c_ramp_start = np.linspace(5.5,2.,5)
        self.p.xvar_r_ramp_start = np.linspace(4.5,2.,5)

        # self.p.xvar_c_ramp_end = np.linspace(2.5,1.,5)
        # self.p.xvar_r_ramp_end = np.linspace(2.5,1.,5)

        # self.p.xvar_t_ramp = np.linspace(7.,12.,5) * 1.e-3

        self.xvarnames = ['self.p.xvar_c_ramp_start','self.p.xvar_r_ramp_start']

        self.trig_ttl = self.get_device("ttl14")

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait * s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for xvar1 in self.p.xvar_c_ramp_start:

            for xvar2 in self.p.xvar_r_ramp_start:

                self.step_time = self.p.t_ramp / self.p.steps

                self.c_ramp = np.linspace(xvar1, self.p.c_ramp_end, self.p.steps)
                self.r_ramp = np.linspace(xvar2, self.p.r_ramp_end, self.p.steps)

                self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()
                self.switch_d2_2d(0)

                self.cmot_d1(self.p.t_d1cmot * s)

                self.trig_ttl.on()
                self.gm(self.p.t_gm * s)

                for n in range(self.steps):
                    delay(-10*us)
                    self.dds.d1_3d_c.set_dds_gamma(v_pd=self.c_ramp[n])
                    delay_mu(self.params.t_rtio_mu)
                    self.dds.d1_3d_r.set_dds_gamma(v_pd=self.r_ramp[n])
                    delay(10*us)

                    with parallel:
                        self.ttl_magnets.off()
                        self.switch_d1_3d(1)
                        self.switch_d2_3d(0)
                    delay(self.step_time)

                # delay(self.p.t_gm * s)

                self.trig_ttl.off()
                
                self.release()
                
                ### abs img
                delay(self.p.t_tof * s)
                self.abs_image()

                self.core.break_realtime()

        # return to mot load state
        self.mot_observe()

    def analyze(self):

        self.p.c_ramp_start = self.p.xvar_c_ramp_start
        self.p.r_ramp_start = self.p.xvar_r_ramp_start

        # self.p.c_ramp_end = self.p.xvar_c_ramp_end
        # self.p.r_ramp_end = self.p.xvar_r_ramp_end

        self.camera.Close()
        
        self.ds.save_data(self)

        print("Done!")
