from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config.dds_calibration import DDS_VVA_Calibration
from kexp.config.ttl_id import ttl_frame
from kexp.util.artiq.async_print import aprint

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

        cal = DDS_VVA_Calibration()

        self.p.v_pd_d1_c = cal.power_fraction_to_vva(.85)
        self.p.v_pd_d1_r = cal.power_fraction_to_vva(.26)

        self.p.xvar_t_lightsheet_hold = np.linspace(15.,100.,10) * 1.e-3

        # self.p.t_lightsheet_hold = 100. * 1.e-3

        # self.p.xvar_t_lightsheet_rampup = np.linspace(2.,18.,20) * 1.e-3

        # self.p.pfrac_lightsheet_ramp = np.linspace(0.0,1.0,200)
        # self.p.xvar_v_pd_lightsheet_ramp_list = cal.power_fraction_to_vva(self.p.pfrac_lightsheet_ramp)

        # self.p.xvar_v_d1cmot_current = np.linspace(.5,1.8,10)

        # self.p.xvar_v_d2cmot_current = np.linspace(.5,1.8,10)

        # self.p.ramp_bool = [0,1]
        # self.p.xvar_t_lightsheet_rampup = np.linspace(3.,20.,2) * 1.e-3
        self.p.t_lightsheet_rampup = 10.e-3
        # self.p.t_longest = np.max(self.p.xvar_t_lightsheet_rampup)

        self.p.xvar_amp_lightsheet_paint = np.linspace(0.,.51,6)
        # self.p.xvar_freq_lightsheet_paint = np.linspace(100.452,164.452,2) * 1.e3

        # self.p.t_lightsheet_hold = 100.e-3

        # self.xvarnames = ['xvar_t_lightsheet_hold']
        # self.xvarnames = ['xvar_t_lightsheet_hold','ramp_bool']
        # self.xvarnames = ['xvar_t_lightsheet_rampup']
        self.xvarnames = ['xvar_t_lightsheet_hold']
        # self.xvarnames = ['xvar_v_d1cmot_current']
        # self.xvarnames = ['xvar_v_d2cmot_current']

        self.p.N_repeats = [2]

        self.finish_build()

    @kernel
    def run(self):
        
        self.init_kernel()

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
    
        for xvar2 in self.p.xvar_t_lightsheet_hold:
            
            # self.lightsheet.set(paint_amplitude=a,v_lightsheet_vva=5.,paint_frequency=xvar2)
            self.lightsheet.set_power(v_lightsheet_vva=5.)

            self.mot(self.p.t_mot_load * s)
            # self.hybrid_mot(self.p.t_mot_load * s)

            ### Turn off push beam and 2D MOT to stop the atomic beam ###
            self.dds.push.off()

            self.cmot_d1(self.p.t_d1cmot * s)
            
            ### GM 1 ###
            self.gm(self.p.t_gm * s)

            self.gm_ramp(self.p.t_gmramp * s)

            # delay(self.p.t_lightsheet_load)
            
            self.release()

            ### GM 2 ###
            # self.gm(t=10.e-6*s, detune_d1=9.2, v_pd_d1_c=self.p.pfrac_c_gmramp_end, v_pd_d1_r=self.p.pfrac_r_gmramp_end)

            self.lightsheet.ramp(t_ramp=self.p.t_lightsheet_rampup)
            # self.lightsheet.on()
            self.release()

            # self.pulse_resonant_mot_beams(1.e-6*s)

            self.ttl.spectrum_trig.on()
            delay(xvar2 * s)
            self.ttl.spectrum_trig.off()

            self.lightsheet.off()

            delay(10.e-6)
            # self.fl_image()
            self.flash_repump()
            self.abs_image()

            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        # self.p.t_lightsheet_rampup = self.p.xvar_t_lightsheet_rampup

        # self.p.v_d1cmot_current = self.p.xvar_v_d1cmot_current

        # self.p.v_d2cmot_current = self.p.xvar_v_d2cmot_current

        self.camera.Close()

        self.ds.save_data(self)

        print("Done!")