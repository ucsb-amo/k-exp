"""Rydberg loss vs BEC density, set by a spill-out of the tweezer before the Rydberg pulse.

Sequence: HF tweezer BEC (tweezer evap 1 + evap 2 on PID2, then the field ramp to i_hf_raman), then
  SPILL:    smoothstep from the evap-2 end (v_pd_hf_tweezer_1064_rampdown2_end, PID2 units) down to v_pd_spill,
            hold t_spill_hold (atoms above the lowered depth leave),
  RE-RAISE: smoothstep back up to the evap-2 end, settle t_spill_settle,
  RYDBERG:  405 + 980 on for t_tweezer_hold, then tweezer off, TOF, absorption image on the Andor.
Both spill ramps use the evap-2 painting law (keep_trap_frequency_constant=True, paint_amp_exponent_hf_tweezer,
default v_pd_max), so the painting amplitude is a function of the power alone and the re-raised trap is the evap-2
end trap: the trap depth during the Rydberg pulse is the same for every v_pd_spill. v_pd_spill = evap-2 end is the
no-spill control with identical timing.

Scan: v_pd_spill (outer) x do_980_pulse [0, 1] (inner): a 980-off / 980-on pair at every density.
Defaults = the 182 A reference (ref182_00.py, 11-04): PID on, EO 418.9 MHz (known line), hold 512 ms, v980 2.8 V,
imaging -568 MHz. For >= 190 A set do_outer_coil_pid = 0 (no PID there, user 2026-11-04) and that field's imaging
detuning / EO frequency.

prepare_hf_tweezers_spill is a copy of Cooling.prepare_hf_tweezers (k-exp/kexp/base/cooling.py sha256 52f1cc9d9200)
with the squeeze / ramp_down_painting branch dropped (unused here), start_pid() made switchable (off -> delay of
the same 80 ms, as the generated --no-pid files), and the spill + re-raise added at the end. scan_kernel follows
HF_experiments/Rydberg/hf_bec_rydberg_scan.py (sha256 4f40f8f2c0d5), as the 11-04..11-08 spectrum / reference runs.
Written 2026-11-08; not yet run on the machine.
"""
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2


class hf_tweezer_rydberg_spill(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera=True, save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      warmup_shots=3)

        # field + imaging (182 A reference; for 193.5 A: 193.5, -618.36e6, do_outer_coil_pid = 0)
        self.p.i_hf_raman = 182.0
        self.p.frequency_detuned_hf_f1m1 = -568.e6
        self.p.do_outer_coil_pid = 1

        self.p.t_tof = 1325.e-6

        # rydberg (as ref182_00.py)
        self.p.do_405_pulse = 1
        self.p.do_980_pulse = 0
        self.p.amp_dds_405 = 0.06
        self.p.frequency_eo_980 = 418.9e6
        self.p.t_tweezer_hold = 512.e-3   # rydberg pulse length (beams on for the whole hold)
        self.p.v_pd_ry_405 = 0.45
        self.p.v_pd_ry_980 = 2.8

        # spill-out (PID2 units, as v_pd_hf_tweezer_1064_rampdown2_end = 0.5)
        self.p.v_pd_spill = self.p.v_pd_hf_tweezer_1064_rampdown2_end   # default = no spill
        self.p.t_spill_rampdown = 100.e-3
        self.p.t_spill_hold = 50.e-3
        self.p.t_spill_rampup = 100.e-3
        self.p.t_spill_settle = 20.e-3

        self.xvar('v_pd_spill', np.linspace(0.34, 0.40, 7))
        self.p.v_pd_spill=0.4
        # self.xvar('v_pd_spill', np.linspace(0.47, 0.50, 7))
        # self.xvar('t_spill_hold', np.linspace(0., 200., 5) * 1.e-3)
        # self.xvar('do_980_pulse', np.array([0, 1]))
        # self.xvar('frequency_eo_980', np.linspace(416., 422., 31) * 1.e6)

        self.p.N_repeats = 3
        self.finish_prepare(shuffle=True)

    @kernel
    def prepare_hf_tweezers_spill(self, do_tweezer_evap_2=True):
        """Cooling.prepare_hf_tweezers (see module docstring) + switchable PID + spill / re-raise."""
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
                                    i_end=self.p.i_hf_lightsheet_evap1_current)

        self.set_shims(0., 0., 0.)

        # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                                         v_start=self.p.v_pd_lightsheet_rampup_end,
                                         v_end=self.p.v_pd_hf_lightsheet_rampdown_end)

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                    i_end=self.p.i_hf_tweezer_load_current)

        self.tweezer.on()
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                                      v_start=0.,
                                      v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                      paint=True, keep_trap_frequency_constant=False,
                                      tau=-self.p.t_hf_tweezer_1064_ramp / 3)
        self.diag.img_tweezer_load_x.trigger()      # diagnostic frames (no-op when off)
        self.diag.img_tweezer_pickoff.trigger()

        # lightsheet ramp down (to off)
        self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                         v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                         v_end=self.p.v_pd_lightsheet_rampdown3_end)

        if self.p.v_pd_lightsheet_rampdown3_end == 0.:
            self.lightsheet.off()

        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                                    i_end=self.p.i_hf_tweezer_evap1_current)

        # tweezer evap 1; painting law (P/P_max)**paint_amp_exponent_hf_tweezer
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                                      v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                      v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                                      paint=True, keep_trap_frequency_constant=True,
                                      paint_exponent=self.p.paint_amp_exponent_hf_tweezer)

        if do_tweezer_evap_2:
            # PID2 start biased low: integral2 is preloaded to 4 V (AO2's efficiency peak) at enable
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

        self.diag.img_tweezer_evap_x.trigger()      # diagnostic frame after the last evap ramp

        self.dac.supply_current_2dmot.set(v=0.)

        self.outer_coil.ramp_supply(t=20.e-3,
                                    i_end=self.p.i_hf_raman)

        if self.p.do_outer_coil_pid == 1:
            self.outer_coil.start_pid()
        else:
            delay(80.e-3)  # = start_pid duration (50 ms supply ramp + 30 ms analog delay): timing unchanged

        delay(30.e-3)

        # ---- spill-out and re-raise (PID2, evap-2 painting law both ways) ----
        self.ttl.pd_scope_trig.pulse(1.e-6)
        self.tweezer.ramp(t=self.p.t_spill_rampdown,
                          v_start=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          v_end=self.p.v_pd_spill,
                          paint=True, keep_trap_frequency_constant=True, low_power=True,
                          cubic_ramp=True,
                          paint_exponent=self.p.paint_amp_exponent_hf_tweezer)
        delay(self.p.t_spill_hold)
        self.tweezer.ramp(t=self.p.t_spill_rampup,
                          v_start=self.p.v_pd_spill,
                          v_end=self.p.v_pd_hf_tweezer_1064_rampdown2_end,
                          paint=True, keep_trap_frequency_constant=True, low_power=True,
                          cubic_ramp=True,
                          paint_exponent=self.p.paint_amp_exponent_hf_tweezer)
        delay(self.p.t_spill_settle)

    @kernel
    def scan_kernel(self):

        self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)

        self.ry_405.set_power(self.p.v_pd_ry_405)
        self.ry_980.set_power(self.p.v_pd_ry_980)
        self.ttl.ry_intensity_pid_clear.pulse(10.e-6)

        self.ry_980.sweep_to(self.p.frequency_eo_980)

        self.prepare_hf_tweezers_spill(do_tweezer_evap_2=True)

        # rydberg pulse in the re-raised trap (same depth for every v_pd_spill)
        if self.p.do_405_pulse == 1:
            self.ry_405.reboot()
            self.ry_405.dds_sw.set_dds(amplitude=self.p.amp_dds_405)
            self.ry_405.on()
        if self.p.do_980_pulse == 1:
            self.ry_980.on()

        delay(self.p.t_tweezer_hold)

        self.ry_405.off()
        self.ry_980.off()
        self.ry_405.ttl_shutter.off()

        delay(40e-3)

        self.tweezer.off()

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
        self.end(expt_filepath)
