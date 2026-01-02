
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base
import numpy as np
from kexp.calibrations import high_field_imaging_detuning
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

from artiq.coredevice.shuttler import DCBias, DDS, Relay, Trigger, Config, shuttler_volt_to_mu

T32 = 1<<32

class mag_trap(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,setup_camera=True,save_data=True,
                    camera_select=cameras.andor,
                    imaging_type=img_types.ABSORPTION)

        self.p.t_tof = 3000.e-6


        self.p.v_pd_hf_lightsheet_rampdown_end = 1.3207384995262181
        self.p.v_hf_tweezer_paint_amp_max = -3.65289250562525
        self.p.i_hf_tweezer_load_current = 192.54126675597212
        self.p.t_hf_tweezer_1064_ramp = 0.27631295278037354
        self.p.v_pd_hf_tweezer_1064_ramp_end = 8.128316756535057
        self.p.i_hf_tweezer_evap1_current = 191.42218915114194
        self.p.t_hf_tweezer_1064_rampdown = 0.34298067957012734
        self.p.v_pd_hf_tweezer_1064_rampdown_end = 0.958238477713867
        self.p.i_hf_tweezer_evap2_current = 193.581357332832
        self.p.t_hf_tweezer_1064_rampdown2 = 0.6453121327954494
        self.p.v_pd_hf_tweezer_1064_rampdown2_end = 0.18801378751362063

        self.p.t_tweezer_hold = 10.e-3

        # self.p.frequency_tweezer_list = [75.8e6, 76.5e6]

        # a_list = [.486,.513]
        # a_list = [.4,.6]
        # a_list = [.5]
        # self.p.amp_tweezer_list = a_list

        self.p.hf_imaging_detuning = -617.5e6 # 193.2

        self.p.amp_imaging = .1
        self.p.imaging_state = 2.

        self.p.N_repeats = 3
        self.p.t_mot_load = 1.

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.hf_imaging_detuning)
        self.dds.imaging.set_dds(amplitude=self.p.amp_imaging)

        # self.switch_d2_2d(1)
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)

        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)

        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.dac.xshim_current_control.linear_ramp(self.p.t_yshim_rampdown,
                                                self.p.v_xshim_current_magtrap,
                                                0.,n=50)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                            i_start=0.,
                            i_end=self.p.i_hf_lightsheet_evap1_current)

        # lightsheet evap 1
        self.lightsheet.ramp(t=self.p.t_hf_lightsheet_rampdown,
                            v_start=self.p.v_pd_lightsheet_rampup_end,
                            v_end=self.p.v_pd_hf_lightsheet_rampdown_end)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_hf_lightsheet_evap1_current,
                            i_end=self.p.i_hf_tweezer_load_current)

        self.tweezer.on()
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_ramp,
                        v_start=0.,
                        v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                        paint=True,keep_trap_frequency_constant=False)

        # lightsheet ramp down (to off)
        self.lightsheet.ramp(t=self.p.t_lightsheet_rampdown3,
                                v_start=self.p.v_pd_hf_lightsheet_rampdown2_end,
                                v_end=self.p.v_pd_lightsheet_rampdown3_end)

        self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_hf_tweezer_load_current,
                            i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1 with constant trap frequency
        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                        v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                        v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                        paint=True,keep_trap_frequency_constant=True)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_hf_tweezer_evap1_current,
                            i_end=self.p.i_hf_tweezer_evap2_current)

        self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                        v_start=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                        v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                        paint=True,keep_trap_frequency_constant=True)

        # self.tweezer.ramp(t=self.p.t_hf_tweezer_1064_rampdown3,
        #                   v_start=tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown2_end),
        #                   v_end=self.p.v_pd_hf_tweezer_1064_rampdown3_end,
        #                   paint=True,keep_trap_frequency_constant=True,low_power=True)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                            i_start=self.p.i_hf_tweezer_evap2_current,
                            i_end=193.2)

        delay(self.p.t_tweezer_hold)

        self.tweezer.off()

        delay(self.p.t_tof)
        self.abs_image()

        # self.tweezer.off()

        self.outer_coil.off()

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

