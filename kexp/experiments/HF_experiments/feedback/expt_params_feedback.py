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

        self.dt_t_raman_pulse_offset = 220.e-9 # non ideal pulse width
        self.t_raman_pulse_ideal = self.t_raman_pi_pulse / 2
        self.t_raman_pulse = self.t_raman_pulse_ideal + self.dt_t_raman_pulse_offset

        # calibration run 66811
        # img amp 0.2, pulse time 5.0e-06 s
        self.frequency_lightshift = 2.84e+04  # Hz

        # # calibration run 66491
        # self.t_img_pulse = 1e-05  # s
        # self.amp_imaging = 0.2
        # self.v_apd_all_up = -0.085716
        # self.v_apd_all_down = -0.23706
        # self.n_photons_per_shot = 2488.7
        # # self.std_n_photons_up = 137.41
        # # self.std_n_photons_down = 79.314
        # self.std_n_photons_per_shot = 108.36 # avg of up/down
        # self.feedback_measurement_midpoint_fraction = 0.4346

        # calibration run 66806
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.1735
        self.v_apd_all_down = -0.21425
        self.n_photons_per_shot = 727.02
        # self.std_n_photons_up = 204.91
        # self.std_n_photons_down = 45.157
        self.std_n_photons_per_shot = 125.03 # avg of up/down
        self.feedback_measurement_midpoint_fraction = 0.41794

        # run 66493 | multi-parameter grid fit result
        self.back_action_coherence = 0.92
    
        self.feedback_measurement_midpoint_remap_enabled = True

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


