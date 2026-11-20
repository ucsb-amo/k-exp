"""Cold low-field atoms near the 33.56 G |1,-1> pole, imaged on the strongest LF line (Claude, 2026-11-19, user request).

Sequence = JK/lf_bec_evap_claude_6_11.py v2c (the file behind the latest LF runs, 93212-93355, 11-06/07), unchanged: HF
cooling path (Cooling.prepare_hf_tweezers line for line) at LF currents matched in scattering length -- sheet 13.54 A,
tweezer load 12.79 A, tweezer evap 1 + 2 13.41 A. What is new is the IMAGING (see below). ExptParams is not changed: every
override is set in prepare(). Analysis + model: C:\\lab\\skynet_log\\outputs\\2026-11-19_13-07_lf_cold\\ (gather.py,
summarize.py, closure.py), log C:\\lab\\skynet_log\\2026-11-19_13-07_1.md.

What the latest LF runs say (v2c settings, 2 us probe at 327 MHz, Andor, clipped OD; 144 runs, nothing excluded):
  - stability 93218-93317 (100 runs x 10 shots per TOF): 1.5 ms 7 px peak OD 0.59 (run-to-run sd 0.07), cloud sigma
    4.8 x 5.1 um; release energy m<v^2>/kB from sigma(1.5 ms) -> sigma(3.0 ms) = 41 +/- 2 nK horizontal, 55 +/- 2 nK vertical.
    This is expansion AT 13.41 A (a ~ 190 a0, kamo), i.e. it includes mean-field release, so it is not a temperature.
  - evap-1 time A/B (93320-93355, 18 pairs, 0.2 s vs 0.3 s): +0.048 +/- 0.025 peak (+1.9 SE); f1a/f1b (93318/93319):
    0.2 vs 0.3 s +0.5 / -0.8 SE. The rule fixed on 11-07 (0.2 s only if all three > 2 SE) is NOT met -> 0.3 s kept.
    Lead only: in both f1 runs 0.10-0.15 s gave the highest peak (0.72-0.75 vs 0.58-0.66 at 0.3 s); parked scan below.
  - Andor look along the tweezer axis (x): no bimodality claim is possible from these images.

IMAGING -- why the sigma+ line (k39_lines.py / closure.py: Breit-Rabi ground + 4P3/2 diagonalisation, decay branching):
  At 38.8 G (13.41 A; field map B = 2.877 G/A I + 0.19 G, uncertain) the 4P3/2 state is Paschen-Back, the ground state is
  not: |1,-1> = mix of |mJ=-1/2, mI=-1/2> and |mJ=+1/2, mI=-3/2>. Every line from |1,-1> is therefore OPEN; an atom
  scatters 1/(1 - closure) photons on average before it falls into F=2 (dark, ~460 MHz away). Lines (model frame, MHz):
      sigma-  +157   strength = closure 0.32  -> 1.5 photons   <- the line used so far (Andor 327-331 MHz measured)
      pair    +230   pi 0.21 (leaks 16 % to |1,0>) / sigma- 0.25
      pi      +305   0.46  -> 1.8 photons
      sigma+  +379   0.66  -> 2.9 photons   <- |mJ'=+3/2, mI=-3/2>, decays only back to |mJ=+1/2, mI=-3/2>
  The Andor probe runs along x and B is along z (k perpendicular to B): any probe polarisation has EQUAL sigma+ and sigma-
  intensity, so the sigma+ line is driven as hard as the sigma- line, with 2x the cross section and 2x the photons per atom
  -> expected ~2x the absorbed signal per atom, ~2x the peak OD. The dose that pumps an atom dark scales as
  photons/strength = 1/(c(1-c)): 4.6 (sigma-) vs 4.4 (sigma+), so the 2 us / camera-setpoint-0.2 dose found best on sigma-
  (#93208, #93211: optimum DOSE, not intensity, because the line is open) is the right start on sigma+ too.
  Where: sigma+ - sigma- spacing (model) 221.7 MHz at 38.8 G (+5.4 MHz/G). Anchor: measured Andor sigma- ~327 MHz at
  13.41 A (#93203, n5 #93217 peak 328) -> sigma+ predicted ~549 MHz. If the 7-21 MHz model/measurement gap of the sigma-
  line is a field-map error instead of a frequency offset, sigma+ sits ~537 MHz. Default scan 516-582 MHz covers both.
  NEVER measured on a stage-4 cloud: 93180 (505-570 MHz) was stage 2 with the old 10 us probe, which showed no sigma-
  either. So the default run below is the sigma+ search, with sigma- reference shots interleaved in the same run.
  Beat lock: offset = 1130.85 MHz - detuning must stay >= 250 MHz -> detuning <= 880 MHz (582 MHz -> offset 549 MHz).
  Alternative kept: IMAGING = '120G' ramps to 41.64 A (~120 G, no pole crossed, a ~ 10 a0 so TOF is near-ballistic) and
  images sigma- at 107.5 MHz (#93192/#93197, measured with the OLD 10 us probe; closure 0.62, same as LF sigma+).
  Never IMAGE_AT_HF for a dense LF cloud: the ramp to 182 A crosses the 162 G pole (#93179).

After the line scan: set FREQUENCY_SIGMA_PLUS to the fitted centre, comment out the line xvar, un-park the TOF xvar.
"""
# End state (same as the v2c file): outer coil at <= 13.54 A during the sequence (41.64 A with '120G'), off after the
# image; cleanup_scan_kernel resets coils. Camera gain = camera config default.
from artiq.experiment import *
from artiq.experiment import delay
from kexp import Base, img_types, cameras
import numpy as np
from kexp.calibrations.tweezer import tweezer_vpd1_to_vpd2

STAGE = 4
CAMERA = 'andor'
IMAGE_AT_HF = False                 # never for a dense LF cloud (162 G pole crossing, #93179)
IMAGING = 'sigma_plus'              # 'sigma_plus' (new, 2.9 photons) | 'sigma_minus' (v2c, 1.5 photons) | '120G'

FREQUENCY_SIGMA_MINUS = 327.e6      # measured at 13.41 A (#93203, #93217); 331.0 +/- 1.2 MHz at 13.01 A (#93198+#93200)
# FREQUENCY_SIGMA_PLUS = 549.e6     # PREDICTED (sigma- + 221.7 MHz model spacing)
FREQUENCY_SIGMA_PLUS = 546.8e6      # #95944, 2026-11-19: Lorentzian 546.8 +/- 0.4 MHz, FWHM 10.6 +/- 1.5, A 12.8 SE (13.41 A, 1.5 ms)
FREQUENCY_120G = 107.5e6            # sigma- at 41.64 A (#93192, #93197; old 10 us probe)
I_120G = 41.64


class lf_bec_cold_claude_19_11(EnvExperiment, Base):

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

        # ---- LF fields (transducer A), same scattering length as the HF stages; unchanged from v2c ----
        self.p.i_lf_lightsheet_evap1_current = 13.54   # flat 13.14-13.94 (#93205)
        self.p.i_lf_tweezer_load_current = 12.79       # flat from 12.59 up (#93204)
        self.p.i_lf_tweezer_evap1_current = 13.41      # best of 12.61-14.41 (#93199/#93201)
        self.p.t_lf_field_hold = 50.e-3
        self.p.i_lf_hold_current = I_120G if IMAGING == '120G' else -1.   # < 0: stay at the evap field
        self.p.t_lf_tweezer_hold = 0.                  # LF loss -30 % in the first 0.1 s (#93207): no hold
        # field climb (user 11-19 "see how high in field you can go, aim for the 160G resonance"): after the hold at
        # i_lf_hold_current, ramp to i_lf_image_current (>= 0) and image there. < 0: image at the hold field (as before).
        self.p.i_lf_image_current = -1.
        self.p.i_hf_raman = 182.

        # evap timings/ends = ExptParams (0.27 s sheet, 0.3 s evap 1 to 0.16 V, 0.3 s evap 2 to 0.5 V; v2c values)
        # self.p.t_hf_tweezer_1064_rampdown = 0.15   # lead only (f1a/f1b), 11-07 rule for 0.2 s not met

        # ---- imaging ----
        self.p.frequency_lf_imaging = {'sigma_plus': FREQUENCY_SIGMA_PLUS, 'sigma_minus': FREQUENCY_SIGMA_MINUS,
                                       '120G': FREQUENCY_120G}[IMAGING]
        # LF probe dose (open line): 2 us at the camera's default setpoint (#93208: 2 us 87 vs 10 us 42 integrated OD).
        self.p.t_imaging_pulse = 2.e-6

        self.p.t_tweezer_hold = 10.e-3
        self.p.t_tof = 1.5e-3                          # the stability-run TOF: cloud at (194, 257) on the Andor

        # (1) DEFAULT: sigma+ line search on the stage-4 cloud, with 3 sigma- reference values (x N_repeats) in the same
        #     shuffled run, so the sigma+/sigma- signal ratio is measured directly. 26 values x 2 = 52 shots (+3 warm-up).
        self.xvar('frequency_lf_imaging',
                  np.concatenate([np.arange(516.e6, 583.e6, 3.e6), [FREQUENCY_SIGMA_MINUS] * 3]))
        # (2) after (1): TOF series on the chosen line (compare 93212, sigma- 0.5-3.5 ms)
        # self.xvar('t_tof', np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]) * 1.e-3)
        # (3) dose on the chosen line (compare #93208/#93211 on sigma-)
        # self.xvar('t_imaging_pulse', np.array([1., 2., 3., 5.]) * 1.e-6)
        # (4) evap-1 time lead (f1a/f1b): 0.1-0.3 s
        # self.xvar('t_hf_tweezer_1064_rampdown', np.array([0.1, 0.15, 0.2, 0.3]))
        # (5) evap-2 end, colder: size shrank at constant integral down to 0.5 V, loss at 0.4 V (#93206, 4 shots/pt)
        # self.xvar('v_pd_hf_tweezer_1064_rampdown2_end', np.array([0.4, 0.45, 0.5, 0.6]))
        self.p.N_repeats = 2

        self.finish_prepare(shuffle=True)

    @kernel
    def scan_kernel(self):
        if self.p.do_image_at_hf == 1.:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_detuned_hf_f1m1)
        else:
            self.set_imaging_detuning(frequency_detuned=self.p.frequency_lf_imaging)

        # ---- Cooling.prepare_hf_tweezers, LF currents (identical to lf_bec_evap_claude_6_11 v2c) ----
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
                self.tweezer.on()
                self.tweezer.exponential_ramp(t=self.p.t_hf_tweezer_1064_ramp,
                                              v_start=0.,
                                              v_end=self.p.v_pd_hf_tweezer_1064_ramp_end,
                                              paint=True, keep_trap_frequency_constant=False,
                                              tau=-self.p.t_hf_tweezer_1064_ramp / 3)
                self.diag.img_tweezer_load_x.trigger()
                # self.diag.img_tweezer_pickoff.trigger()   # pickoff basler parked in camera_id, 2026-11-14
                # lightsheet ramp down (to off), HF
                self.lightsheet.exponential_ramp(t=self.p.t_lightsheet_rampdown3,
                                                 v_start=self.p.v_pd_hf_lightsheet_rampdown_end,
                                                 v_end=self.p.v_pd_lightsheet_rampdown3_end)
                if self.p.v_pd_lightsheet_rampdown3_end == 0.:
                    self.lightsheet.off()

                if self.p.lf_stage >= 3.:
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp2,
                                                i_end=self.p.i_lf_tweezer_evap1_current)
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
                    # '120G' imaging: ramp up with no pole crossed (|1,-1> poles at 33.56 and 162.35 G)
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                                i_end=self.p.i_lf_hold_current)
                delay(self.p.t_lf_tweezer_hold)

                if self.p.i_lf_image_current >= 0.:
                    # field climb: back down to the imaging field (no new pole below the hold field is crossed
                    # unless the hold field was above 162.35 G)
                    self.outer_coil.ramp_supply(t=self.p.t_feshbach_field_ramp,
                                                i_end=self.p.i_lf_image_current)

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
