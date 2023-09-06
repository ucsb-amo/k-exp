from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base

import numpy as np

dv = -0.1
dvlist = np.linspace(0.,1.,10)

class light_sheet(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "mot tof"

        ## Parameters

        self.p = self.params

        self.p.t_tof = 10.e-6

        self.p.N_shots = 10
        self.p.N_repeats = 1
        # self.p.t_test = 10.0e-3
        # self.p.t_lightsheet_load = np.linspace(0.0,self.p.t_test,self.p.N_shots)
        self.p.t_lightsheet_hold = 10.e-3
        
        self.p.n_lightsheet_rampup_steps = 100
        self.p.t_lightsheet_rampup = np.linspace(1,10,5) * 1.e-3
        self.p.v_pd_lightsheet_rampup_start = 0.0
        self.p.v_pd_lightsheet_rampup_end = 4.0

        self.p.t_lightsheet_hold = 5.e-3

        self.p.use_lightsheet_bool = [1,0]
        self.p.N_repeats = 5

        self.xvarnames = ['xvar_amp_lightsheet']

        self.finish_build()

    @kernel
    def lightsheet_rampup(self, t=dv, v_pd_lightsheet_list=dv):

        if t == dv:
            t = self.p.t_lightsheet_rampup
        if v_pd_lightsheet_list == dvlist:
            v_pd_lightsheet_list = self.p.v_pd_lightsheet_ramp_list

        self.dds.lightsheet.set_dds(
            frequency=self.p.frequency_ao_lightsheet,
            amplitude=self.p.amp_lightsheet,
            v_pd=self.p.v_pd_lightsheet_rampup_start)
        self.dds.lightsheet.on()

        dt_lightsheet_rampup = t / self.p.n_lightsheet_rampup_steps

        for v in self.p.v_pd_lightsheet_ramp_list:
            self.dds.lightsheet.update_dac_setpoint(v)
            delay(dt_lightsheet_rampup)

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.p.t_grab_start_wait*s)
        
        self.kill_mot(self.p.t_mot_kill * s)

        for use_lightsheet in self.p.use_lightsheet_bool:

            self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()
            self.switch_d2_2d(0)

            self.cmot_d1(self.p.t_d1cmot * s)

            # self.trig_ttl.on()
            self.gm(self.p.t_gm * s)
            # self.trig_ttl.off()

            self.gm_ramp(self.p.t_gmramp * s)
            
            if use_lightsheet:
                self.light_sheet_rampup(self.p.t_lightsheet_rampup)
            else:
                delay(self.p.t_lightsheet_rampup)
            self.switch_d1_3d(0)
            delay(self.p.t_lightsheet_hold)
            if use_lightsheet:
                self.dds.light_sheet.off()

            ### abs img
            delay(self.p.t_tof * s)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")