"""Low-field (50 G) tweezer-BEC Rydberg pulse (45S), Claude 2026-11-19, user request. NOT RUN YET.

Sequence:
1. LF BEC = JK/lf_bec_evap_claude_6_11.py STAGE 4, unchanged (Cooling.prepare_hf_tweezers line for line with LF
   currents: sheet 13.54 A, tweezer load 12.79 A, tweezer evap 1+2 13.41 A ~ 38.8 G).
2. Ramp to I_RYDBERG = 17.31 A = 50 G on the LF field map B ~ 2.877 G/A * I + 0.19 G (anchored on the two measured
   poles 11.6 A = 33.56 G (#93177) and 195 A = 561.14 G (user); uncertain, the I->B mapping is not accurate).
   No pole between 38.8 and 50 G (next is 162 G); the scattering length at 50 G is NOT the evap one -- not quoted.
   Wait t_lf_field_settle (20 ms, my choice, not measured) for the coil.
3. Rydberg pulse as JK/Rydberg/hf_tweezer_rydberg_spectrum.py (405 + 980 on for t_tweezer_hold, 40 ms, tweezer off),
   at 50 G. EO frequencies from the user 2026-11-19: 405 EO 459.6 MHz (Siglent); 980 EO "-599.2 MHz" (RF consultant).
   As edited by the user 11-19: 980 pulse OFF, scan do_405_pulse [0, 1].
4. Image at 50 G with the Andor (no ramp up through the 162 G pole: that destroyed the LF BEC, #93179).

Imaging at 50 G is UNMEASURED. Measured Andor sigma- line: 331.0 +/- 1.2 MHz at 13.01 A (#93198/#93200), ~107.5 MHz
at 41.64 A (#93192/#93197). Model (ground Breit-Rabi -> 4P3/2 mJ=-3/2, offset fixed on the 13.01 A point) gives
291.8 MHz at 50 G (-3.1 MHz/G) but misses the 41.64 A point by -9.9 MHz; linear interpolation between the two
measured points gives 297.4. Default 295 MHz. Run IMAGING_CHECK = True first (beams off, 275-315 MHz scan).

980 EO source: the user (2026-11-19) says the RF consultant drives the 980 EO now. kexp/base/devices.py still selects
the Siglent (da677d25, 11-17, "980 source back to siglent"), so THIS FILE ONLY swaps ry_980's source to
rf_consultant_980 (S/N 517) after Base.__init__ and re-records params.ry_980_rf_consultant = 1; devices.py is not
changed. Consultant values are read from beacon/beacon/tpi/rf_consultant_id.py at prepare (11-19 working copy:
default 417 MHz / +1 dBm, max +3 dBm, 100-1000 MHz; was -17 dBm / max -0.01 dBm / 700 MHz at HEAD): the frequency
check uses its limits, and run() sets the EO amplitude once to its default (params.amplitude_dbm_ry_980_eo) -- a
default otherwise applies only on init, so the device would keep its last amplitude. The end-of-run reset walks the
frequency back to the default (417 MHz); the amplitude is left at the default. The user's 980 value was "-599.2 MHz": an RF frequency has no sign, so 599.2 MHz is written. The sideband
is set by the lock, not here; lock_status records the wavemeter target with eo_shift_direction = -1 (devices.py) --
if the 980 now runs on the other sideband the per-shot lock record is wrong. prepare() refuses any EO value outside
its source's range. Cross-check only: the ry_line_vs_current.ipynb physics model (fitted 505-555 G) extrapolated to
50 G gives ~426 MHz EO in the HF-run convention, 173 MHz from 599.2; not used.

LF lifetime at 13.41 A was ~0.5-1 s with fast early loss (#93207); at 50 G unknown. DO_980_OFF_REFERENCE gives the
980-off baseline in the same run.
"""
import numpy as np
from artiq.experiment import *
from artiq.language.core import delay, kernel
from kexp import Base, img_types, cameras
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

I_RYDBERG = 17.31            # A, 50 G on the LF field map
F_EO_405_MHZ = 459.6         # user, 2026-11-19
F_EO_980_MHZ = 599.2         # user 2026-11-19 ("-599.2 MHz"; sign = sideband, see docstring)
DO_980_OFF_REFERENCE = True  # xvar do_405_pulse [0, 1] (user edit 11-19; 980 pulse off)
IMAGING_CHECK = False        # True: beams off, scan the 50 G imaging line instead (do this first)

EO_405_RANGE_MHZ = (65., 500.)    # siglent_405 (kexp/config/siglent_id.py); it clamps silently outside


class lf_tweezer_rydberg_spectrum(EnvExperiment, Base):

    def prepare(self):
        Base.__init__(self, setup_camera=True, save_data=True,
                      camera_select=cameras.andor,
                      imaging_type=img_types.ABSORPTION,
                      diagnostic_images=True,
                      warmup_shots=3,
                      mot_preload=True)

        # ---- 980 EO driven by the RF consultant (this file only; devices.py selects the Siglent) ----
        rf_980 = self.rf_consultant.rf_consultant_980
        self.ry_980.rf_source = rf_980
        self.ry_980.siglent = rf_980
        self.ry_980.uses_rf_consultant = True
        self.params.ry_980_rf_consultant = 1
        self.rf_980 = rf_980
        self.p.amplitude_dbm_ry_980_eo = float(rf_980.amplitude_dbm_default)
        print(f"ry_980: fiber EO driven by RF consultant rf_consultant_980 (S/N {rf_980.serial}) -- set in this file; "
              f"{rf_980.min_frequency/1e6:g}-{rf_980.max_frequency/1e6:g} MHz, amplitude "
              f"{self.p.amplitude_dbm_ry_980_eo:g} dBm (max {rf_980.max_amplitude_dbm:g})")

        if not IMAGING_CHECK:
            if not rf_980.min_frequency <= F_EO_980_MHZ * 1.e6 <= rf_980.max_frequency:
                raise ValueError(f"980 EO {F_EO_980_MHZ} MHz is outside rf_consultant_980's range "
                                 f"{rf_980.min_frequency/1e6:g}-{rf_980.max_frequency/1e6:g} MHz.")
            lo, hi = EO_405_RANGE_MHZ
            if not lo <= F_EO_405_MHZ <= hi:
                raise ValueError(f"405 EO {F_EO_405_MHZ} MHz is outside siglent_405's range {lo}-{hi} MHz "
                                 f"(the driver would clamp it silently).")

        # ---- LF BEC fields (transducer A), from lf_bec_evap_claude_6_11.py ----
        self.p.i_lf_lightsheet_evap1_current = 13.54
        self.p.i_lf_tweezer_load_current = 12.79
        self.p.i_lf_tweezer_evap1_current = 13.41
        # ---- Rydberg / imaging field ----
        self.p.i_lf_rydberg_current = I_RYDBERG
        self.p.t_lf_field_settle = 20.e-3

        # ---- imaging at 50 G (absolute detuning, Hz), weak probe ----
        # self.p.frequency_lf_imaging = 295.e6  # model estimate, 2026-11-19
        self.p.frequency_lf_imaging = 305.e6  #95969, 2026-11-19 (Lorentzian 304.97 +/- 0.83 MHz, FWHM 12, at 17.31 A)
        self.p.t_imaging_pulse = 2.e-6
        self.p.t_tof = 1325.e-6

        # ---- Rydberg beams, from hf_tweezer_rydberg_spectrum.py ----
        self.p.amp_dds_405 = 0.06
        self.p.v_pd_ry_405 = 0.45
        self.p.v_pd_ry_980 = 1.0
        self.p.t_tweezer_hold = 0.3
        self.p.frequency_eo_405 = F_EO_405_MHZ * 1.e6
        self.p.frequency_eo_980 = F_EO_980_MHZ * 1.e6

        if IMAGING_CHECK:
            self.p.do_405_pulse = 0
            self.p.do_980_pulse = 0
            self.p.t_tweezer_hold = 10.e-3
            self.xvar('frequency_lf_imaging', np.arange(275.e6, 316.e6, 2.5e6))
            self.p.N_repeats = 2
        else:
            self.p.do_405_pulse = 1
            self.p.do_980_pulse = 0
            if DO_980_OFF_REFERENCE:
                self.xvar('do_405_pulse', [0, 1])
            # self.xvar('frequency_eo_980', np.round(np.arange(..., ..., 0.2), 1) * 1.e6)
            self.p.N_repeats = 10

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        self.set_imaging_detuning(frequency_detuned=self.p.frequency_lf_imaging)

        if self.p.do_405_pulse == 1 or self.p.do_980_pulse == 1:
            self.ry_405.set_power(self.p.v_pd_ry_405)
            self.ry_980.set_power(self.p.v_pd_ry_980)
            self.ttl.ry_intensity_pid_clear.pulse(10.e-6)
            self.ry_405.sweep_to(self.p.frequency_eo_405)
            self.ry_980.sweep_to(self.p.frequency_eo_980)

        # ---- LF BEC: Cooling.prepare_hf_tweezers with LF currents (lf_bec_evap_claude_6_11.py, STAGE 4) ----
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

        # lightsheet evap 1
        self.lightsheet.exponential_ramp(t=self.p.t_hf_lightsheet_rampdown,
                                         v_start=self.p.v_pd_lightsheet_rampup_end,
                                         v_end=self.p.v_pd_hf_lightsheet_rampdown_end)
        # tweezer load
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                    i_end=self.p.i_lf_tweezer_load_current)
        self.tweezer.on()
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                                      v_start=0.,
                                      v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                      paint=True, keep_trap_frequency_constant=False,
                                      tau=-self.p.t_hf_tweezer_1064_ramp / 3)
        self.diag.img_tweezer_load_x.trigger()
        self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                         v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                         v_end=self.p.v_pd_lightsheet_rampdown3_end)
        if self.p.v_pd_lightsheet_rampdown3_end == 0.:
            self.lightsheet.off()

        # tweezer evap 1
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                                    i_end=self.p.i_lf_tweezer_evap1_current)
        self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_rampdown,
                                      v_start=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                      v_end=self.p.v_pd_hf_tweezer_1064_rampdown_end,
                                      paint=True, keep_trap_frequency_constant=True,
                                      paint_exponent=self.p.paint_amp_exponent_hf_tweezer)
        # tweezer evap 2 (same field), PID2 start biased low
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
        self.diag.img_tweezer_evap_x.trigger()
        self.dac.supply_current_2dmot.set(v=0.)

        # ---- to 50 G ----
        self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                    i_end=self.p.i_lf_rydberg_current)
        delay(self.p.t_lf_field_settle)

        # ---- Rydberg pulse at 50 G ----
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
        self.rf_980.set_amplitude(self.p.amplitude_dbm_ry_980_eo)
        self.load_2D_mot(self.p.t_2D_mot_load_delay)
        self.scan()

    def analyze(self):
        import os
        expt_filepath = os.path.abspath(__file__)
        self.end(expt_filepath, restart_monitor=False)
