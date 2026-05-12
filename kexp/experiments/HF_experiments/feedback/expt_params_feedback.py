from kexp.config import ExptParams as expt_params_kexp
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        self.feedback_grid_size = 31
        self.N_pulses = 20
        self.feedback_fractional_grid_center_offset = 2.0
        self.feedback_fractional_initial_offset = 0.0
        self.feedback_guess_span_Omega = 5.0

        self.t_raman_pulse = 4.874e-06 #66470, 2026-05-11
        self.t_raman_pulse_ideal = self.t_raman_pi_pulse / 2
        # difference = 88.3 ns

        # calibration run 66446
        # img amp 0.2, pulse time 1.0e-05 s
        self.frequency_lightshift = 2.99e+04  # Hz

        # calibration run 66466
        self.t_img_pulse = 1e-05  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.080826
        self.v_apd_all_down = -0.23474
        self.n_photons_per_shot = 2488.9
        # self.n_std_photons_up = 85.074
        # self.n_std_photons_down = 72.512
        self.n_std_photons_per_shot = 78.793 # avg of up/down

        self.back_action_coherence = 0.729097
        # feedback midpoint from calibration run 66472
        self.feedback_measurement_midpoint_remap_enabled = True
        self.feedback_measurement_midpoint_fraction = 0.444598801

        # run 66415
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.792175653
        self.feedback_apd_map_b = 0.126581972
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_calculation_slack_compensation_mu = int64(0.61 * self.feedback_grid_size * 1.e3) + 20000 if self.feedback_grid_size > 10 else int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(4000) & ~7 # int64(1260)

        self.delta_t_mu = int64(104)

        ### other
        self.phase_offset = 0.0

        self.t_tweezer_hold = 30.e-3


