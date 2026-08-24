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

        self.feedback_grid_size = 21
        self.N_pulses = 20

        self.feedback_fractional_initial_offset = 0.0
        self.feedback_guess_span_Omega = 8.0

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
        self.t_raman_pulse_ideal = self.t_raman_pulse - 127.e-9

        # calibration run 76224
        # img amp 0.2, pulse time 5.0e-06 s
        self.frequency_lightshift = 3.46e+04  # Hz
                
        # calibration run 76227
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.1331
        self.v_apd_all_down = -0.17931
        self.n_photons_per_shot = 784.6
        # self.std_n_photons_up = 69.696
        # self.std_n_photons_down = 180.7
        # self.std_n_photons_per_shot = 125.2 # avg of up/down
        self.std_n_photons_per_shot = 180.7 # using down std
        self.feedback_measurement_midpoint_fraction = 0.3237

        # run 76228 | multi-parameter grid fit result
        self.back_action_coherence = 0.7563

        self.feedback_measurement_midpoint_remap_enabled = True

        # run 66415
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.792175653
        self.feedback_apd_map_b = 0.126581972
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_between_pulses_mu = int64(0)
        self.t_calculation_slack_compensation_mu = int64(0.7 * self.feedback_grid_size * 1.e3) + 15000 if self.feedback_grid_size > 10 else int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(800) & ~7 # int64(1260)
        # self.delta_t_mu = int64(2000)

        self.t_ffu_dds_pipeline_latency = int64(79)
        self.t_io_update_pretrigger_mu = int64(32)
        self.t_ffu_pipeline_latency_fudge_mu = int64(0)

        ### randomized raman pulse times
        # Each shot draws its own list of N_pulses raman pulse times, uniform
        # in [min_frac, max_frac] * t_raman_pi_pulse, from a single RNG stream
        # seeded once per run (see FeedbackExpt.get_new_t_raman_pulse_list).
        # t_raman_pulse_seed = 0 --> unseeded (fresh entropy each run); the
        # seed actually used is always recorded in t_raman_pulse_seed_used, and
        # the drawn times are saved per shot in data.t_raman_pulse.
        self.t_raman_pulse_random_bool = 1
        self.t_raman_pulse_seed = 0
        self.t_raman_pulse_seed_used = 0
        self.t_raman_pulse_min_frac_pi = 1/3
        self.t_raman_pulse_max_frac_pi = 2/3
        # per-shot drawn pulse times; populated in finish_prepare / scan_kernel
        self.t_raman_pulse_list = np.array([self.t_raman_pulse])

        ### other
        self.pulse_list_span_Omega = 0.
        self.pulse_list_seed = 0
        self.phase_offset = 0.0
        
        self.t_tweezer_hold = 30.e-3


