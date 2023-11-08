from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config.dds_calibration import DDS_VVA_Calibration

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=True, absorption_image=False)
        Base.__init__(self)

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        # self.p.t_tof = np.linspace(1200,2000,self.p.N_shots) * 1.e-6 # mot
        # self.p.t_tof = np.linspace(2000,3500,self.p.N_shots) * 1.e-6 # cmot
        # self.p.t_tof = np.linspace(1000,3000,self.p.N_shots) * 1.e-6 # d1 cmot
        # self.p.t_tof = np.linspace(6000,9000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(7000,10000,self.p.N_shots) * 1.e-6 # gm
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # tweezer
        # self.p.t_tof = np.linspace(20,100,self.p.N_shots) * 1.e-6 # mot_reload

        # cmot_ramp_start = self.p.v_mot_current
        # self.p.xvar_cmot_ramp_end = np.linspace(.8,1.8,6)
        # self.cmot_ramp_steps = 10
        # self.cmot_ramp_time = 1000.e-6 * s
        # self.p.ramps = []
        # for p in self.p.xvar_cmot_ramp_end:
        #     self.p.ramps.append(np.linspace(cmot_ramp_start,p,self.cmot_ramp_steps))

        self.p.xvar_t_lightsheet_hold = np.linspace(20.,500.,4) * 1.e-3

        # self.p.xvar_t_lightsheet_rampup = np.linspace(2.,10.,6) * 1.e-3
        
        self.p.xvar_detune_gm2 = np.linspace(6.,12.,8)
        # self.p.xvar_t_gm2 = np.linspace(.5,8.,6) *1.e-3

        cal = DDS_VVA_Calibration()

        # self.p.v_pd_d1_c = cal.power_fraction_to_vva(.85)
        # self.p.v_pd_d1_r = cal.power_fraction_to_vva(.26)

        self.p.xvar_pfrac_d1_c_gm = np.linspace(0.1,1.0,6)
        self.p.xvar_pfrac_d1_r_gm = np.linspace(0.1,1.0,6)

        cal = self.dds.dds_vva_calibration

        self.p.xvar_v_pd_c_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_c_gm)
        self.p.xvar_v_pd_r_gm = cal.power_fraction_to_vva(self.p.xvar_pfrac_d1_r_gm)

        
        # self.p.xvar_v_d1cmot_current = np.linspace(.7,1.7,6)

        # self.p.xvar_v_d2cmot_current = np.linspace(.7,1.7,6)

        self.xvarnames = ['xvar_detune_gm2','xvar_t_lightsheet_hold']
        # self.xvarnames = ['xvar_detune_gm2','xvar_t_lightsheet_hold']
        # self.xvarnames = ['xvar_v_pd_d1_c_gm2','xvar_v_pd_d1_r_gm2']
        # self.xvarnames = ['xvar_v_d2cmot_current', 'xvar_v_d1cmot_current']
        # self.xvarnames = ['xvar_t_lightsheet_hold','xvar_v_d2cmot_current']

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)
        
        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)

        for xvar1 in self.p.xvar_detune_gm2:
            for xvar2 in self.p.xvar_t_lightsheet_hold:

                self.lightsheet.set_power(v_lightsheet_vva=5.)

                self.mot(self.p.t_mot_load * s)

                self.dds.push.off()

                self.ttl.pd_scope_trig.on()
                self.cmot_d1(self.p.t_d1cmot * s)
            
                ### GM 1 ###
                self.gm(self.p.t_gm * s)

                self.gm_ramp(self.p.t_gmramp * s)

                # delay(self.p.t_lightsheet_load)
                
                self.release()

                ### GM 2 ###
                self.gm(t=10.e-6 * s, detune_d1=xvar1, v_pd_d1_c=self.p.pfrac_c_gmramp_end, v_pd_d1_r=self.p.pfrac_r_gmramp_end)

                self.lightsheet.ramp(t_ramp=self.p.t_lightsheet_rampup)
                self.ttl.pd_scope_trig.off()

                self.release()

                delay(xvar2 * s)
                self.lightsheet.off()
                
                delay(10.e-6)
                # self.fl_image()
                self.flash_repump()
                self.abs_image()

                self.core.break_realtime()

                delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        # self.p.t_lightsheet_hold = self.p.xvar_t_lightsheet_hold
        # self.p.t_gm = self.p.xvar_t_gm2
        # self.p.detune_gm2 = self.p.xvar_detune_gm2

        # self.p.v_pd_d1_c_gm2 = self.p.xvar_v_pd_d1_c_gm2
        # self.p.v_pd_d1_r_gm2 = self.p.xvar_v_pd_d1_r_gm2

        # self.p.v_d1cmot_current = self.p.xvar_v_d1cmot_current
        # self.p.v_d2cmot_current = self.p.xvar_v_d2cmot_current

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")