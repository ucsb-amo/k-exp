"""Low-field BEC near the 33.56 G |1,-1> Feshbach resonance (Claude, 2026-11-06, user request).

v2 (21:3x 11-06): the sequence is Cooling.prepare_hf_tweezers line for line (same lightsheet / tweezer powers, ramps and
timings -> same density path), with the three HF currents replaced by LF currents chosen for the SAME scattering length
(kamo coupled-channels tables; field map anchored on the measured poles: 195 A (user) = 561.14 G, 11.6 A (#93177 loss)
= 33.56 G, i.e. B ~ 2.877 G/A * I + 0.19 G):
    sheet evap   HF 192.3 A  179 a0  ->  13.54 A      tweezer load  HF 193.3 A  301 a0  ->  12.79 A
    tweezer evap 1 + 2 (one field, as at HF)  HF 193.0 A  252 a0  ->  13.01 A
v1 (runs 93156-93178, LF library sheet ramps, LF fields 14-16 A) is kept in C:\\lab\\skynet_log\\outputs\\2026-11-06_20-10_lf_bec.
ExptParams is not changed: every override is set in prepare() below.

STAGE: how far the sequence goes before the image.
    0  sheet load, field ramp to i_lf_lightsheet_evap1_current, hold t_lf_field_hold
    1  + HF sheet evap
    2  + field ramp to i_lf_tweezer_load_current, HF tweezer load, HF sheet ramp-down
    3  + field ramp to i_lf_tweezer_evap1_current, HF tweezer evap 1
    4  + HF tweezer evap 2 (same field)
Then: optional ramp to i_lf_hold_current (>= 0) and hold t_lf_tweezer_hold; optionally (do_image_at_hf) ramp to i_hf_raman
with the PID and image at frequency_detuned_hf_f1m1; else image at the LF field at frequency_lf_imaging (absolute detuning,
Hz). MEASURED (11-06 night): Andor sigma- line at the LF evap field 331.0 MHz at 13.01 A (#93198/#93200); at 41.64 A ~107.5 MHz (#93192/#93197); evap field best ~13.41 A (#93199/#93201); stage 4 = compact cloud, expands like the HF BEC (#93193/#93195 vs #93196). Model LF line positions (k39_lines.py in the outputs folder, offset fixed on the xy Basler lines #93156/#93157): at 12.8 A
sigma- ~326, sigma-/pi pair ~393 (the xy Basler line), pi ~467, sigma+ ~537 MHz (strengths .32/.2+.25/.46/.66).
"""
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

STAGE = 4
CAMERA = 'andor'
IMAGE_AT_HF = False


class lf_bec_evap_claude_6_11(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self,
                      save_data=True,
                      camera_select=getattr(cameras, CAMERA),
                      imaging_type=img_types.ABSORPTION,
                      diagnostic_images=True,
                      warmup_shots=3,
                      mot_preload=True)

        self.p.lf_stage = float(STAGE)
        self.p.do_image_at_hf = 1. if IMAGE_AT_HF else 0.

        # ---- LF fields (transducer A), same scattering length as the HF stages (see docstring) ----
        self.p.i_lf_lightsheet_evap1_current = 13.54
        self.p.i_lf_tweezer_load_current = 12.79
        # self.p.i_lf_tweezer_evap1_current = 13.01  # matched a (252 a0)
        self.p.i_lf_tweezer_evap1_current = 13.41  # #93199/#93201: compact peak best at 13.41 A (imaged at 120 G)
        self.p.t_lf_field_hold = 50.e-3
        self.p.i_lf_hold_current = -1.   # < 0: stay at the stage's field
        self.p.t_lf_tweezer_hold = 0.
        self.p.i_hf_raman = 182.

        # ---- LF imaging: absolute detuning (Hz) ----
        # Andor sigma- line imaged at the evap field: 331.0 +/- 1.2 MHz at 13.01 A, FWHM 19.6 (#93198 + #93200);
        # model slope ~ -9.2 MHz/A -> ~327 MHz at 13.41 A. At 41.64 A (~120 G, no pole crossing) the Andor line is ~107.5 MHz (#93192, #93197).
        self.p.frequency_lf_imaging = 327.e6
        # self.xvar('frequency_lf_imaging', np.arange(505.e6, 571.e6, 2.5e6))
        self.xvar('t_tof', np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]) * 1.e-3)

        # LF probe dose: the LF imaging transition is open -> short pulse. At 327 MHz, 1.0 ms TOF: 2 us integral 87 vs
        # 10 us 42 (camera setpoint 0.2, #93208); 0.1 V x 5 us = 88 (#93211), 0.4 V x 10 us = 19 (#93210).
        self.p.t_imaging_pulse = 2.e-6

        self.p.t_tweezer_hold = 10.e-3
        self.p.t_tof = 1325.e-6 if CAMERA == 'andor' else 900.e-6
        # self.xvar('t_tof', np.linspace(200., 2500., 7) * 1.e-6)
        self.p.N_repeats = 4

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        if self.p.do_image_at_hf == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        else:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_lf_imaging)

        # ---- Cooling.prepare_hf_tweezers, LF currents ----
        self.mot(self.p.t_mot_load)
        self.dds.push.off()
        self.cmot_d1(self.p.t_d1cmot * s)
        self.gm(self.p.t_gm * s)
        self.gm_ramp(self.p.t_gmramp)
        self.magtrap_and_load_lightsheet(do_magtrap_rampup=False)

        self.outer_coil.on()
        self.outer_coil.set_voltage()
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                                    i_start=0.,
                                    i_end=self.p.i_lf_lightsheet_evap1_current)
        self.set_shims(0., 0., 0.)
        i_now = self.p.i_lf_lightsheet_evap1_current

        if self.p.lf_stage < 1.:
            delay(self.p.t_lf_field_hold)
            self.lightsheet.off()
        else:
            # lightsheet evap 1 (HF)
            self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                                             v_start=self.p.v_pd_lightsheet_rampup_end,
                                             v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
            if self.p.lf_stage < 2.:
                self.lightsheet.off()
            else:
                self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                            i_end=self.p.i_lf_tweezer_load_current)
                i_now = self.p.i_lf_tweezer_load_current
                self.tweezer.on()
                self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                                              v_start=0.,
                                              v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                              paint=True, keep_trap_frequency_constant=False,
                                              tau=-self.p.t_hf_tweezer_1064_ramp / 3)
                self.diag.img_tweezer_load_x.trigger()
                self.diag.img_tweezer_pickoff.trigger()
                # lightsheet ramp down (to off), HF
                self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                                 v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                                 v_end=self.p.v_pd_lightsheet_rampdown3_end)
                if self.p.v_pd_lightsheet_rampdown3_end == 0.:
                    self.lightsheet.off()

                if self.p.lf_stage >= 3.:
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                                                i_end=self.p.i_lf_tweezer_evap1_current)
                    i_now = self.p.i_lf_tweezer_evap1_current
                    # tweezer evap 1 (HF)
                    self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                                                  v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                                  v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                                                  paint=True, keep_trap_frequency_constant=True,
                                                  paint_exponent=self.p.paint_amp_exponent_hf_tweezer)
                if self.p.lf_stage >= 4.:
                    # tweezer evap 2 (HF), PID2 start biased low
                    v_start2 = tweezer_vpd1_to_vpd2(self.p.v_pd_hf_tweezer_1064_rampdown_end) \
                        * self.p.fraction_hf_tweezer_evap2_start
                    self.ttl.pd_scope_trig.pulse(1.e-6)
                    if self.p.do_hold_painting_hf_tweezer_evap2 == 1.:
                        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                                                      v_start=v_start2,
                                                      v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                                                      paint=True, keep_trap_frequency_constant=False,
                                                      v_awg_am_max=self.tweezer.paint_amp_dac.v,
                                                      low_power=True)
                    else:
                        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown2,
                                                      v_start=v_start2,
                                                      v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                                                      paint=True, keep_trap_frequency_constant=True, low_power=True,
                                                      paint_exponent=self.p.paint_amp_exponent_hf_tweezer)
                if self.p.lf_stage >= 3.:
                    self.diag.img_tweezer_evap_x.trigger()

                self.dac.supply_current_2dmot.set(v=0.)

                if self.p.i_lf_hold_current >= 0.:
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                                i_end=self.p.i_lf_hold_current)
                    i_now = self.p.i_lf_hold_current
                delay(self.p.t_lf_tweezer_hold)

                if self.p.do_image_at_hf == 1.:
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_rampup,
                                                i_end=self.p.i_hf_raman)
                    self.outer_coil.start_pid()
                    delay(30.e-3)

                delay(self.p.t_tweezer_hold)
                self.tweezer.off()

        self.dac.supply_current_2dmot.set(v=0.)
        delay(self.p.t_tof)
        self.abs_image()
        self.outer_coil.off()

    @kernel
    def run(self):
        self.init_kernel()
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)
