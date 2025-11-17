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

        # self.xvar('frequency_detuned_imaging_m1',np.arange(250.,450.,8)*1.e6)

        # self.xvar('beans',[0]*3)
        
        # self.xvar('t_tof',np.linspace(100.,2000.,10)*1.e-6)
        self.p.t_tof = 20.e-6

        self.p.t_tweezer_hold = 1.e-3

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_load_current)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.yshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                   self.p.v_yshim_current_magtrap,
                                                   0.,n=500)

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
        
        self.tweezer.on(paint=True)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                          v_start=0.,
                          v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                          paint=True,keep_trap_frequency_constant=False,
                          v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)
        
        self.lightsheet.off()

        delay(self.p.t_tweezer_hold)
        self.tweezer.off()

        delay(self.p.t_tof)

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