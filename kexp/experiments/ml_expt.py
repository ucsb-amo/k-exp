
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types
import numpy as np
from kexp.util.artiq.async_print import aprint
from kexp.control.slm.slm import SLM
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2
from kexp.calibrations.imaging import high_field_imaging_detuning

class tweezer_load(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,camera_select='andor',save_data=True)

        self.p.t_tof = 1500.e-6

        self.p.frequency_tweezer_list = [74.e6]
        a_list = [.2]
        self.p.amp_tweezer_list = a_list


        self.p.i_lf_tweezer_load_current = 15.846091852300088
        self.p.v_pd_lf_tweezer_1064_ramp_end = 7.959237208905826
        self.p.v_lf_tweezer_paint_amp_max = 4.532594159007786
        self.p.i_lf_tweezer_evap1_current = 14.74210574693286
        self.p.v_pd_lf_tweezer_1064_rampdown_end = 3.2753230485544793
        self.p.t_lf_tweezer_1064_rampdown = 0.27067086915901206
        self.p.i_lf_tweezer_evap2_current = 13.009635581243174
        self.p.v_pd_lf_tweezer_1064_rampdown2_end = 0.13220249434060424
        self.p.t_lf_tweezer_1064_rampdown2 = 0.7280729309714208

        self.p.t_mot_load = 1.
        self.p.N_repeats = 1

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_high_field_imaging(i_outer=self.p.i_lf_tweezer_evap2_current,
                                    pid_bool=False)

        self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet()

        # feshbach field on, ramp up to field 1  
        self.outer_coil.on()
        # delay(1.e-3)
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_lf_lightsheet_evap1_current)

        self.set_shims(v_zshim_current=0.,
                        v_yshim_current=0.,
                        v_xshim_current=0.)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_lf_lightsheet_rampdown_end)

        # feshbach field ramp to field 2
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                 i_start=self.p.i_lf_lightsheet_evap1_current,
                 i_end=self.p.i_lf_tweezer_load_current)

        self.tweezer.on(paint=False)
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_ramp,
                        v_start=0.,
                        v_end=self.p.v_pd_lf_tweezer_1064_ramp_end,
                        paint=True,keep_trap_frequency_constant=False,v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lf_lightsheet_rampdown2,
                            v_start=self.p.v_pd_lf_lightsheet_rampdown_end,
                            v_end=self.p.v_pd_lightsheet_rampdown2_end)

        # delay(self.p.t_lightsheet_hold)
        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_lightsheet_evap1_current,
                            i_end=self.p.i_lf_tweezer_evap1_current)


        # # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown,
                        v_start=self.p.v_pd_lf_tweezer_1064_ramp_end,
                        v_end=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                        paint=True,keep_trap_frequency_constant=True,v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_lf_tweezer_evap1_current,
                            i_end=self.p.i_lf_tweezer_evap2_current)

        # # # tweezer evap 2 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_lf_tweezer_1064_rampdown2,
                        v_start=self.p.v_pd_lf_tweezer_1064_rampdown_end,
                        v_end=self.p.v_pd_lf_tweezer_1064_rampdown2_end,
                        paint=True,keep_trap_frequency_constant=True,v_awg_am_max=self.p.v_lf_tweezer_paint_amp_max)

        self.tweezer.off()

        delay(self.p.t_tof)

        self.abs_image()

        self.outer_coil.off()
        self.outer_coil.discharge()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()
        # self.mot_observe()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath)

