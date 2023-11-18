from artiq.experiment import *
from artiq.experiment import delay, parallel, sequential, delay_mu
from kexp import Base
from kexp.config.dds_calibration import DDS_VVA_Calibration
from kexp.config.ttl_id import ttl_frame
from kexp.util.artiq.async_print import aprint

import numpy as np

class tof(EnvExperiment, Base):

    def build(self):
        # Base.__init__(self, basler_imaging=False, absorption_image=False, andor_imaging=True)
        Base.__init__(self)

        self.run_info._run_description = "scan lightsheet hold"

        ## Parameters

        self.p = self.params

        self.p.t_mot_load = 1.

        cal = DDS_VVA_Calibration()

        # self.p.v_pd_d1_c = cal.power_fraction_to_vva(.85)
        # self.p.v_pd_d1_r = cal.power_fraction_to_vva(.26)

        self.p.xvar_t_lightsheet_hold = np.linspace(15.,100.,10) * 1.e-3
        self.p.xvar_t_tweezer_hold = np.linspace(0.,1.,5) * 1.e-3
        # self.p.xvar_exposure_time = np.linspace(.005,.01,2) * 1.e-3

        # self.p.xvar_frequency_detuned_imaging = np.linspace(490.,580.,20) * 1.e6

        # self.p.n_ramps = 10
        # self.p.xvar_v_pd_lightsheet = np.linspace(.5,5.,self.p.n_ramps)

        # self.p.ramp_list = np.empty((self.p.n_ramps, self.p.n_lightsheet_rampup_steps))

        # for idx in range(len(self.p.xvar_v_pd_lightsheet)):
        #     self.p.ramp_list[idx] = np.linspace(0, self.p.xvar_v_pd_lightsheet[idx], self.p.n_lightsheet_rampup_steps)

        # self.p.xvar_t_tof = np.linspace(2.,200.,20) * 1.e-6
        # self.p.xvar_t_lightsheet_hold = np.logspace(np.log10(15.*1.e-3),np.log10(7.),20)
        # self.p.xvar_t_mot_load = np.linspace(0.25,3.,10)

        self.p.tweezer_bool = [0,1]
        # self.p.t_tof = np.linspace(50.,1000.,10) * 1.e-6
        self.p.t_tof = 10.e-6

        # self.p.t_lightsheet_hold = 20.e-3

        self.p.t_optical_pumping = 100.e-6 * s

        self.camera_params.exposure_time = 1000.e-6 * s

        # self.p.t_mot_kill_time = np.linspace(0.,2500.,10) * 1.e-6
        # self.p.t_max = np.max(self.p.t_mot_kill_time)

        self.xvarnames = ['xvar_t_tweezer_hold']
        # self.xvarnames = ['t_tof']

        self.p.N_repeats = 2

        self.finish_build(shuffle=False)

    @kernel
    def run(self):
        
        self.init_kernel()

        # self.dds.second_imaging.set_dds(frequency=102.425e6,amplitude=0.188)

        self.StartTriggeredGrab()
        delay(self.camera_params.connection_delay*s)

        self.load_2D_mot(self.p.t_2D_mot_load_delay * s)
    
        # for f in self.p.xvar_frequency_detuned_imaging:
        # for xvar in self.p.t_tof:
        for xvar in self.p.xvar_t_tweezer_hold:

            # self.camera_params.exposure_time = xvar

            # self.set_imaging_detuning(detuning=xvar)
            
            # self.lightsheet.set(paint_amplitude=a,v_lightsheet_vva=5.,paint_frequency=xvar2)
            # self.lightsheet.set_power(v_lightsheet_vva=5.)

            # self.set_imaging_detuning(detuning=f) 

            self.mot(self.p.t_mot_load * s)
            self.dds.push.off()
            self.cmot_d1(self.p.t_d1cmot * s)
            self.gm(self.p.t_gm * s)
            self.gm_ramp(self.p.t_gmramp * s) 

            self.release()
            
            # self.set_magnet_current(v=v)
            # self.ttl.magnets.on()
            
            self.lightsheet.ramp(t=self.p.t_lightsheet_rampup)

            delay(20.e-3)
            
            # self.ttl.magnets.off()

            self.tweezer_ramp(self.p.t_tweezer_ramp)
            
            # self.lightsheet.ramp_down(t=self.p.t_lightsheet_rampup)

            self.lightsheet.off()

            delay(xvar)

            # self.dds.second_imaging.on()

            # self.dds.tweezer.off()

            # self.optical_pumping(t=self.p.t_optical_pumping,
            #                         t_bias_rampup=0.,
            #                         v_zshim_current=self.p.v_zshim_current_op)
            
            # delay(xvar)

            self.flash_repump()
            # self.fl_image()
            self.abs_image()

            # self.dds.second_imaging.off()
            
            self.core.break_realtime()
            
            delay(self.p.t_recover)

        self.mot_observe()

    def analyze(self):

        self.camera.Close()

        import os
        expt_filepath = os.path.abspath(__file__)
        self.ds.save_data(self, expt_filepath)

        print("Done!")