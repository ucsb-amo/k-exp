from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,
                    camera_select=cameras.xy_basler,
                    save_data=True)


        self.p.v_pd_lf_lightsheet_rampdown_end = 1.0
        # self.xvar('v_pd_lf_lightsheet_rampdown_end',np.linspace(0.3,1.4,12))
        self.p.i_lf_lightsheet_evap1_current=14.0
        # self.xvar('i_lf_lightsheet_evap1_current',np.linspace(13.,16,8))
        self.p.i_lf_tweezer_load_current=14.0
        # self.xvar('i_lf_tweezer_load_current',np.linspace(12.,18,10))
        self.camera_params.amp_imaging = 0.2

        self.xvar('t_tof',np.linspace(100.,1600.,7)*1.e-6)
        self.p.t_tof = 1000.e-6

        self.p.t_tweezer_hold = 1.e-3

        self.p.imaging_freq=385.e6
        # self.xvar('imaging_freq',np.linspace(340.,450.,10)*1.e6)


        self.p.t_mot_load = 1.
        self.p.N_repeats = 1
        # self.p.imaging_state = 2.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.imaging_freq)
        self.imaging.set_power(self.camera_params.amp_imaging)


        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        # self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
        #                                         self.p.v_yshim_current_magtrap,
        #                                         0.,n=500)

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_lf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_lf_lightsheet_rampdown_end)
        
        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_lightsheet_evap1_current,
                            i_end=self.p.i_lf_tweezer_load_current)
        
        
        self.lightsheet.off()

        delay(self.p.t_tof)
        # self.flash_repump()

        self.abs_image()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)