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
        self.feedback_grid_size = 11 # user, 2026-10-28
        self.N_pulses = 17
        self.N_repeats = 5

        ### hypothesis grid (kexp.base.feedback, 'hypothesis grid'; user, 2026-10-28)
        # Convention 2: the grid's full width in Hz; the initial drive - resonance as
        # a fraction of the largest allowed offset (full span / 2 - half a step;
        # -1..1, > 0 = drive above resonance); the grid shift in grid steps
        # (-1/2..1/2, > 0 = grid up in frequency, resonance off grid by that much).
        # feedback_guess_span_Omega and feedback_initial_offset_Omega are derived
        # (compute_feedback_grid); setting them by hand is refused. Run files without
        # feedback_grid_convention are convention 1 (span and offset in Omega).
        self.feedback_grid_convention = 2
        # self.frequency_feedback_grid_full_span = 12.75e3 # 0.1 Omega at t_pi 3.9229 us (#89418): the old 0.05 Omega half-width
        self.frequency_feedback_grid_full_span = 12.e3 # user, 2026-10-28 (with feedback_grid_size 11: step 1.2 kHz)
        self.feedback_fractional_initial_offset = 0.0
        self.feedback_grid_shift = 0.0
        # Convention 1 only: centre the hypothesis grid on the exact initial offset
        # (1, 2026-09-27) or on round(offset) (0, as run files without this key).
        # Convention 2 always centres on the exact offset.
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
        # AOM/switch turn-on latency: the programmed pulse is this much longer
        # than the coherent rotation area it actually produces. Only the
        # difference matters, so it stays scalar even when the pulse times
        # themselves are randomized. t_raman_pulse_ideal is derived from it.
        self.t_raman_pulse_offset = 127.e-9
        self.t_raman_pulse_ideal = self.t_raman_pulse - self.t_raman_pulse_offset

        # calibration run 78267
        # img amp 0.2, pulse time 5.0e-06 s
        # self.frequency_lightshift = 4.061e+04  # Hz, +/- 1.5e+03 Hz, imaging amp 0.2 #80654
        # run 83203 | RabiJointPosterior (apd_joint_calibration, f free, t0 127 ns), nuisances verdict PASS
        self.frequency_lightshift = 2.384e+04  # Hz, +/- 1.6e+03 Hz, imaging amp 0.2, t_pulse 5 us #89424
                
        # calibration run 89425 (S_z endpoints from 'fit', deg-2 S_z response fit)
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.12456
        self.v_apd_all_down = -0.16908
        self.n_photons_per_shot = 691.7
        # self.std_n_photons_up = 132
        # self.std_n_photons_down = 97.663
        # self.std_n_photons_per_shot = 114.83 # avg of up/down
        self.std_n_photons_per_shot = 97.663 # using down std
        self.feedback_measurement_midpoint_fraction = 0.50278

        self.back_action_coherence = 0.8445 #88845-88847, 2026-10-26  # open-loop simcheck re-measure (SIMCHECK_PREREG.md sha c3448752, fit_remeasure.py 489c70c0): C0 under the live model, APD scale fixed at map #88792,88794 (34.21 mV), +/- 0.006, Raman lock 44.89 GHz, f_LS 26.2 kHz

        # State-dependent read model (2026-10-11, EXPLORATORY; kexp.base.feedback.READ_TWIST_SIGN):
        # the read's z twist per unit s_z (rad) and the coherence slope per unit s_z, both at the
        # read. 0 = off = the constant model above, bit for bit. theta11 (86179-86181, post hoc):
        # dphi = -1.432 + 0.869 s_z rad, R = 0.738 + 0.193 s_z -- not applied until the simulation
        # check says it helps and the user says go.

        self.read_twist_per_sz = 1.350 #88845-88847, 2026-10-26  # open-loop simcheck re-measure (SIMCHECK_PREREG.md sha c3448752): twist per unit s_z, +/- 0.063, Raman lock 44.89 GHz, f_LS 26.2 kHz
        self.back_action_coherence_slope = 0.0
        self.read_alpha_lightshift = 1.191 #88845-88847, 2026-10-26
        self.feedback_read_model = -1.0
        # read model 1 (theta11's M1-p2); used only on shots with feedback_read_model = 1
        self.read_model1_alpha_lightshift = 1.432
        self.read_model1_twist_per_sz = 0.869
        self.read_model1_coherence = 0.739
        self.read_model1_coherence_slope = 0.0

        self.feedback_measurement_midpoint_remap_enabled = True

        # run 66415
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.792175653
        self.feedback_apd_map_b = 0.126581972
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_between_pulses_mu = int64(0)
        self.t_calculation_slack_compensation_mu = int64(0.7 * self.feedback_grid_size * 1.e3) + 15000 if self.feedback_grid_size > 10 else int64(10000)
        # +10 us for the new integrator window (main, 2026-09-29 16:30): the APD sample now lands
        # 5.7 us after the imaging pulse (was 1.0 us), 4.7 us out of the post-sample budget
        # (~47 -> ~42 us vs a ~16 us posterior); +10 us restores it with ~5 us more margin
        # against the rare ~40 us DRTIO stall (83670-83672). User: "increase slack as necessary",
        # 2026-09-29. 29.7 us -> 39.7 us at grid 21.
        self.t_calculation_slack_compensation_mu = self.t_calculation_slack_compensation_mu + int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(800) & ~7 # int64(1260)
        # self.delta_t_mu = int64(2000)

        self.t_ffu_dds_pipeline_latency = int64(79)
        self.t_io_update_pretrigger_mu = int64(32)
        self.t_ffu_pipeline_latency_fudge_mu = int64(0)

        ### randomized raman pulse times
        # Each shot's list of N_pulses raman pulse times (uniform in
        # [min_frac, max_frac] * t_raman_pi_pulse) is a pure function of
        # t_raman_pulse_seed: equal seeds give identical lists, so the seed can
        # be scanned with xvar. t_raman_pulse_seed = 0 --> a fresh seed is drawn
        # for every shot. The seed actually used is saved per shot in
        # data.t_raman_pulse_seed and the drawn times in data.t_raman_pulse
        # (see FeedbackExpt.get_new_t_raman_pulse_list).
        self.t_raman_pulse_random_bool = 1
        self.t_raman_pulse_seed = 532
        self.t_raman_pulse_min_frac_pi = 1/2
        self.t_raman_pulse_max_frac_pi = 1
        # per-shot drawn pulse times; populated in finish_prepare / scan_kernel
        self.t_raman_pulse_list = np.array([self.t_raman_pulse])

        ### other
        self.pulse_list_span_Omega = 0.
        self.pulse_list_seed = 0
        self.phase_offset = 0.0
        # 1: FeedbackExpt rewrites the SLM phase-dot mask every shot (see
        # base_expt_feedback.scan_kernel); 0: only at init_kernel (as before 2026-09-28)
        # self.slm_mask_every_shot = 0
        self.slm_mask_every_shot = 1 # 2026-09-30: default on for every FeedbackExpt (user: all APD experiments write the SLM mask per shot; 83472/83473 contrast 32 -> 14 mV with init-only)
        # 1: every shot starts with APD read (all up) - resonant pi pulse - APD read
        # (all down), stored in data.preshot_apd [up, down] (a per-run contrast), and the
        # feedback model starts all down. FeedbackExpt.finish_prepare derives
        # feedback_initial_sz from it (-1 with the pre-shot, +1 without); runs without
        # the key replay as spin-up (user, 2026-09-28).
        self.preshot_contrast = 0
        self.t_preshot_gap = 10.e-6
        self.feedback_initial_sz = 1.0
        # With the pre-shot: > 0 moves the APD endpoints every shot toward the
        # pre-shot reads, v <- v + gain*(read - v), from the calibration at the start
        # of each run; N_photons_per_shot rescales with the contrast, std_n is kept
        # (Feedback.update_shot_endpoints). 0 = the calibration for every shot.
        # Offline test 2026-09-28 (sim_preshot): 1 (raw per shot) was worse than the
        # calibration, 0.15 better when the readout drifted.
        self.preshot_endpoint_gain = 0.
        # a per-shot range below this x the calibration range is not taken (guard)
        self.preshot_endpoint_min_range_fraction = 0.25

        self.t_tweezer_hold = 30.e-3

        ### interleaved readout calibration (an interleaved sub-scan, waxx
        ### Expt.add_sub_scan; FeedbackExpt.calibration_kernel). 2026-10-09.
        # 1: every cal_every_n_shots data shots (and before the first) the run
        # takes one pair of readout points -- the prepared state (t_raman_pulse
        # 0, all up) and after a resonant pi (all down) -- recorded raw in the
        # run's file (ad.cal). 0: no sub-scan, the run is as before.
        self.cal_enabled = 0
        self.cal_every_n_shots = 20
        # reads per point, taken at the data shot's read spacing (mode 0) or
        # the calibration run's (mode 1, cal_t_between_reads_mu)
        self.cal_n_reads = 5
        # readout modes cycled event by event: 0 = the data shot's readout
        # (FeedbackExpt.calibration_read: measurement()'s integrator timeline,
        # fast frequency update set up), 1 = the calibration run's readout
        # (apd_voltage_vs_state_2: warmup_imaging, integrated_imaging_pulse at
        # cal_t_between_reads_mu). Both, so the two readouts are compared
        # inside one run; [0.] for the data readout only.
        self.cal_readout_modes = np.array([0., 1.])
        self.cal_t_between_reads_mu = int64(25000)
        # 1: the pair's order (up, down) is reversed on every other event
        self.cal_alternate = 1
        # 0 in phase 1: the points are recorded and evaluated on the host only;
        # the kernel's readout constants never change during the run. Any
        # other value is refused (not built).
        self.cal_apply = 0
        # the sub-scan's point parameters (set per point by the scan loop)
        self.cal_readout_mode = 0.

        self.compute_feedback_grid()

    def compute_feedback_grid(self):
        """The kernel's Omega-unit grid parameters from the base ones (run by
        compute_derived: every shot, and with the scanned arrays at the end of
        the run). Convention 2: feedback_guess_span_Omega and
        feedback_initial_offset_Omega from frequency_feedback_grid_full_span,
        feedback_grid_size, t_raman_pi_pulse and feedback_fractional_initial_offset.
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
            # two scanned base parameters whose arrays do not broadcast (the end of a
            # 2-D scan): no one derived array describes the shots -- NaN, not a stale value
            span_Omega, offset_Omega = np.nan, np.nan
        self.feedback_guess_span_Omega = span_Omega
        self._feedback_guess_span_Omega_derived = span_Omega
        self.feedback_initial_offset_Omega = offset_Omega


