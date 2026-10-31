from kexp.config import ExptParams as expt_params_kexp
import numpy as np
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        # run 76036
        # self.frequency_detuned_hf_f1m1 = -574.51e6
        # self.frequency_detuned_hf_f10 = -465.38e6
        # self.frequency_detuned_hf_midpoint = -519.94e6

        self.update_raman_frequency_bool = 0
        self.include_photon_noise = 1

        # self.feedback_grid_size = 21
        # self.feedback_grid_size = 11 # user, 2026-10-28
        self.feedback_grid_size = 21 # user, 2026-10-30: as the FB/NA files (fbna_FB_c7s0.py)
        self.N_pulses = 17
        self.N_repeats = 5

        ### hypothesis grid (kexp.base.feedback, 'hypothesis grid')
        # full width in Hz; initial drive - resonance as a fraction of the largest allowed offset
        # (-1..1, > 0 = drive above resonance); grid shift in grid steps (-1/2..1/2, > 0 = grid up).
        # feedback_guess_span_Omega and feedback_initial_offset_Omega are derived; setting them is refused.
        self.feedback_grid_convention = 2
        # self.frequency_feedback_grid_full_span = 12.75e3 # 0.1 Omega at t_pi 3.9229 us (#89418): the old 0.05 Omega half-width
        # self.frequency_feedback_grid_full_span = 12.e3 # user, 2026-10-28 (with feedback_grid_size 11: step 1.2 kHz)
        self.frequency_feedback_grid_full_span = 8844.4 # user, 2026-10-30: as the FB/NA files (step 442.2 Hz)
        self.feedback_fractional_initial_offset = 0.0
        self.feedback_grid_shift = 0.0
        # 1: a tie for the posterior maximum gives the mean of the tied points, which may be
        # off grid (user, 2026-10-30; Feedback.map_frequency). 0, or no key: the first maximum
        self.feedback_map_tie_mean = 1
        # convention 1 only: 1 = centred on the exact offset, 0 = on round(offset)
        self.feedback_grid_center_exact_offset = 0.
        # self.feedback_guess_span_Omega = 0.1 / 2 # convention 1: grid HALF-width in Omega

        # Threshold for adaptive remesh: if posterior std < threshold * Omega,
        # halve the grid span and re-centre on omega_raman.  0.0 = disabled.
        self.feedback_remesh_threshold_Omega = 0.0
        self.remesh_interpolate_posterior = 0
        self.remesh_interpolate_states = 0
        self.remesh_expand_clipped_grid_to_requested_size = 1
        self.remesh_scale_factor = 0.5
        self.remesh_threshold_scale_factor = 0.5
        self.remesh_after_n_good_shots = 1
        self.remesh_reset_counter_threshold_fraction = 1.5
        self.n_initial_shots_before_remesh = 2

        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        # AOM/switch turn-on latency: programmed pulse minus coherent rotation time
        self.t_raman_pulse_offset = 127.e-9
        self.t_raman_pulse_ideal = self.t_raman_pulse - self.t_raman_pulse_offset

        # calibration run 78267
        # img amp 0.2, pulse time 5.0e-06 s
        # self.frequency_lightshift = 4.061e+04  # Hz, +/- 1.5e+03 Hz, imaging amp 0.2 #80654
        # run 83203 | RabiJointPosterior (apd_joint_calibration, f free, t0 127 ns), nuisances verdict PASS
        # self.frequency_lightshift = 2.384e+04  # Hz, +/- 1.6e+03 Hz, imaging amp 0.2, t_pulse 5 us #89424
        # self.frequency_lightshift = 2.337e+04  # Hz, +/- 1.5e+03 Hz, imaging amp 0.2, t_pulse 5 us #89769, 2026-10-29
        # self.frequency_lightshift = 2.465e+04  # Hz, +/- 3.6e+03 Hz, imaging amp 0.2, t_pulse 5 us #89935, 2026-10-29
        self.frequency_lightshift = 2.375e+04  # Hz, +/- 1.8e+03 Hz, imaging amp 0.2, t_pulse 5 us #90201, 2026-10-30
                
        # calibration run 89425 (S_z endpoints from 'fit', deg-2 S_z response fit)
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        # APD readout calibration, runs 89442 (sigma_z), python -m kexp.analysis.apd_state_mapping
        # (retry of the suspicious 89440: agrees within 0.6 / 1.8 mV, contrast +6 %)
        # APD readout calibration, run 89746 (sigma_z 7 pt, t_pi #89744), python -m kexp.analysis.apd_state_mapping --degree 1
        # (curvature resolved in 89746: deg-2 midpoint 0.691 +/- 0.055, 3.5 sigma; degree 1 kept per the standing procedure)
        # self.v_apd_all_up = -0.12456
        # self.v_apd_all_up = -0.12918 #89442, 2026-10-29  # S_z=+1 of the degree-1 single-shot fit, +/- 0.0013 V
        # self.v_apd_all_up = -0.13232 #89746, 2026-10-29  # S_z=+1 of the degree-1 single-shot fit, +/- 0.0013 V
        # self.v_apd_all_up = -0.13814 #89937, 2026-10-29  # S_z=+1 of the degree-1 single-shot fit, +/- 0.0017 V; retry 89938 -0.13693 agrees
        # self.v_apd_all_up = -0.13801 #89960, 2026-10-29  # periodic recal 3-pt, +/- 0.0014 V; retry 89962 -0.13895 agrees
        # self.v_apd_all_up = -0.13616 #90019, 2026-10-30  # refit-block recal 3-pt, +/- 0.0020 V; retry 90020 -0.13648 agrees
        self.v_apd_all_up = -0.1409 #90202, 2026-10-30  # S_z=+1 of the degree-1 single-shot fit, +/- 0.0021 V
        # self.v_apd_all_down = -0.16908
        # self.v_apd_all_down = -0.16948 #89442, 2026-10-29  # S_z=-1 of the degree-1 single-shot fit, +/- 0.0013 V
        # self.v_apd_all_down = -0.16677 #89746, 2026-10-29  # S_z=-1 of the degree-1 single-shot fit, +/- 0.0014 V
        # self.v_apd_all_down = -0.16945 #89937, 2026-10-29  # S_z=-1 of the degree-1 single-shot fit, +/- 0.0018 V; retry 89938 -0.16817 agrees
        # self.v_apd_all_down = -0.16109 #89960, 2026-10-29  # periodic recal 3-pt, +/- 0.0015 V; retry 89962 -0.16114 agrees (contrast 31.3 -> 23.1 mV)
        # self.v_apd_all_down = -0.17389 #90019, 2026-10-30  # refit-block recal 3-pt, +/- 0.0021 V; retry 90020 -0.17579 agrees (contrast 23.1 -> 37.7 mV)
        self.v_apd_all_down = -0.17856 #90202, 2026-10-30  # S_z=-1 of the degree-1 single-shot fit, +/- 0.0022 V
        # self.n_photons_per_shot = 691.7
        # self.n_photons_per_shot = 614.32 #89442, 2026-10-29  # scope integral, up minus down per pulse, +/- 30
        # self.n_photons_per_shot = 538.19 #89746, 2026-10-29  # scope integral, up minus down per pulse, +/- 33
        # self.n_photons_per_shot = 415.32 #89937, 2026-10-29  # scope integral, up minus down per pulse, +/- 51
        # self.n_photons_per_shot = 308.16 #89960, 2026-10-29  # scope integral, up minus down per pulse, +/- 42
        # self.n_photons_per_shot = 545.02 #90019, 2026-10-30  # scope integral, up minus down per pulse, +/- 53
        self.n_photons_per_shot = 551.95 #90202, 2026-10-30  # scope integral, up minus down per pulse, +/- 53
        # self.std_n_photons_up = 132
        # self.std_n_photons_down = 97.663
        # self.std_n_photons_per_shot = 114.83 # avg of up/down
        # self.std_n_photons_per_shot = 97.663 # using down std
        # self.std_n_photons_per_shot = 131.75 #89442, 2026-10-29  # 614.3 * 8.64 mV / 40.30 mV (within-run, up = the larger)
        # self.std_n_photons_per_shot = 141.53 #89746, 2026-10-29  # 538.2 * 9.06 mV / 34.45 mV (within-run, down = the larger)
        # self.std_n_photons_per_shot = 130.23 #89937, 2026-10-29  # 415.3 * 9.82 mV / 31.31 mV (within-run, down)
        # self.std_n_photons_per_shot = 112.31 #89960, 2026-10-29  # 308.2 * 8.41 mV / 23.08 mV (within-run, up)
        # self.std_n_photons_per_shot = 124.0 #90019, 2026-10-30  # 545 * 8.59 mV / 37.73 mV (within-run, up)
        self.std_n_photons_per_shot = 151.98 #90202, 2026-10-30  # 552 * 10.37 mV / 37.66 mV (within-run, up)
        # self.feedback_measurement_midpoint_fraction = 0.50278
        # self.feedback_measurement_midpoint_fraction = 0.5 #89442, 2026-10-29  # linear map (quadratic term not resolved)
        # self.feedback_measurement_midpoint_fraction = 0.5 #89746, 2026-10-29  # linear map (degree 1 by procedure; deg-2 midpoint 0.691 +/- 0.055 NOT used)
        # self.feedback_measurement_midpoint_fraction = 0.5 #89937, 2026-10-29  # linear map (quadratic term not resolved)
        # self.feedback_measurement_midpoint_fraction = 0.5 #89960, 2026-10-29  # linear map
        # self.feedback_measurement_midpoint_fraction = 0.5 #90019, 2026-10-30  # linear map
        self.feedback_measurement_midpoint_fraction = 0.5 #90202, 2026-10-30  # linear map (degree 1 by procedure; deg-2 midpoint 0.85 +/- 0.07 NOT used)

        self.back_action_coherence = 0.8445 #88845-88847, 2026-10-26  # open-loop simcheck re-measure (SIMCHECK_PREREG.md sha c3448752, fit_remeasure.py 489c70c0): C0 under the live model, APD scale fixed at map #88792,88794 (34.21 mV), +/- 0.006, Raman lock 44.89 GHz, f_LS 26.2 kHz

        # State-dependent read model (READ_TWIST_SIGN in kexp.base.feedback): the read's z twist (rad)
        # and coherence slope per unit s_z at the read. 0 = off.
        self.read_twist_per_sz = 0.976 #89437, 2026-10-28  # check_twist Ramsey phase vs s_z, +/- 0.111 (chi2_red 1.67, 3 dof, errors scaled), Raman lock 46.055 GHz (SD 2.8 MHz); contrast/sin(theta) not flat; reference assumed pi
        # self.read_twist_per_sz = 1.350 #88845-88847, 2026-10-26  # open-loop simcheck re-measure (SIMCHECK_PREREG.md sha c3448752): twist per unit s_z, +/- 0.063, Raman lock 44.89 GHz, f_LS 26.2 kHz
        self.back_action_coherence_slope = 0.0
        self.read_alpha_lightshift = 0.948 #89437, 2026-10-28  # same fit, +/- 0.046; intercept carries the reference phase and Raman detuning
        # self.read_alpha_lightshift = 1.191 #88845-88847, 2026-10-26
        self.feedback_measurement_midpoint_remap_enabled = True

        ### timing
        self.t_between_pulses_mu = int64(0)
        self.t_calculation_slack_compensation_mu = int64(0.7 * self.feedback_grid_size * 1.e3) + 15000 if self.feedback_grid_size > 10 else int64(10000)
        # +10 us: the new integrator window moved the APD sample 4.7 us later, and ~40 us DRTIO stalls
        # happen (83670-83672); 29.7 -> 39.7 us at grid 21 (user, 2026-09-29)
        self.t_calculation_slack_compensation_mu = self.t_calculation_slack_compensation_mu + int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(800) & ~7 # int64(1260)

        ### randomized raman pulse times
        # uniform in [min_frac, max_frac] * t_raman_pi_pulse, a pure function of the seed; seed 0 = a
        # fresh seed every shot. Seed and times are saved per shot.
        self.t_raman_pulse_random_bool = 1
        self.t_raman_pulse_seed = 532
        self.t_raman_pulse_min_frac_pi = 1/2
        self.t_raman_pulse_max_frac_pi = 1
        # per-shot drawn pulse times; populated in finish_prepare / scan_kernel
        self.t_raman_pulse_list = np.array([self.t_raman_pulse])

        ### other
        self.pulse_list_span_Omega = 0.
        self.pulse_list_seed = 0
        # 1: FeedbackExpt rewrites the SLM phase-dot mask every shot (see
        # base_expt_feedback.scan_kernel); 0: only at init_kernel (as before 2026-09-28)
        # self.slm_mask_every_shot = 0
        self.slm_mask_every_shot = 1 # 2026-09-30: default on for every FeedbackExpt (user: all APD experiments write the SLM mask per shot; 83472/83473 contrast 32 -> 14 mV with init-only)

        self.t_tweezer_hold = 30.e-3

        ### interleaved readout calibration (waxx Expt.add_sub_scan; FeedbackExpt.calibration_kernel)
        # 1: every cal_every_n_shots data shots (and before the first), one all-up + all-down pair of
        # raw readout points (ad.cal). Evaluated on the host; the kernel's constants never change.
        self.cal_enabled = 0
        self.cal_every_n_shots = 20
        self.cal_n_reads = 5
        # cycled event by event: 0 = the data shot's readout, 1 = the calibration run's
        # (apd_voltage_vs_state_2); [0.] for the data readout only
        self.cal_readout_modes = np.array([0., 1.])
        self.cal_t_between_reads_mu = int64(25000)
        # gap between the point's raman pulse and its first read
        self.cal_t_raman_to_read = 10.e-6
        self.cal_alternate = 1 # 1: reverse the pair's order on every other event
        self.cal_apply = 0 # any other value is refused: the in-run apply path is not built
        self.cal_readout_mode = 0. # set per point by the scan loop

        self.compute_feedback_grid()

    def compute_feedback_grid(self):
        """The kernel's Omega-unit grid parameters from the base ones (run by compute_derived).
        Convention 1: the offset is already in Omega and is copied."""
        if not hasattr(self, "feedback_grid_convention"):
            return # expt_params_kexp.__init__ runs compute_derived before these exist
        from kexp.base.feedback import feedback_grid_derived
        if int(np.ravel(self.feedback_grid_convention)[0]) < 2:
            self.feedback_initial_offset_Omega = self.feedback_fractional_initial_offset
            return
        try:
            span_Omega, offset_Omega = feedback_grid_derived(
                self.frequency_feedback_grid_full_span, self.feedback_grid_size,
                self.t_raman_pi_pulse, self.feedback_fractional_initial_offset)
        except ValueError:
            # scanned arrays that do not broadcast (end of a 2-D scan): NaN, not a stale value
            span_Omega, offset_Omega = np.nan, np.nan
        self.feedback_guess_span_Omega = span_Omega
        self._feedback_guess_span_Omega_derived = span_Omega
        self.feedback_initial_offset_Omega = offset_Omega


