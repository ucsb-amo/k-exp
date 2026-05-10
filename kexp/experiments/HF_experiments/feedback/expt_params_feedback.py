from kexp.config import ExptParams as expt_params_kexp
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        self.feedback_grid_size = 21
        self.N_pulses = 20
        self.feedback_fractional_grid_center_offset = 2.0
        self.feedback_fractional_initial_offset = 0.0
        self.feedback_guess_span_Omega = 5.0

        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        self.t_raman_pulse_ideal = self.t_raman_pi_pulse / 2

        # calibration run 66387
        # img amp 0.2, pulse time 1.0e-05 s
        self.frequency_lightshift = 3.43e+04  # Hz

        # calibration run 66391
        self.t_img_pulse = 1e-05  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.086901
        self.v_apd_all_down = -0.23444
        self.n_photons_per_shot = 2420.7
        # self.std_n_photons_up = 152.53
        # self.std_n_photons_down = 82.568
        self.n_std_photons_per_shot = 117.55 # avg of up/down

        self.back_action_coherence = 0.78

        # Optional APD linear remap y = a*x + b.
        # Applied in kexp.base.feedback.Feedback before convert_measurement.
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.519336098
        self.feedback_apd_map_b = 0.102252872
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_calculation_slack_compensation_mu = int64(0.61 * self.feedback_grid_size * 1.e3) + 15000 if self.feedback_grid_size > 10 else int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(4000) & ~7 # int64(1260)

        self.delta_t_mu = int64(104)

        ### other
        self.phase_offset = 0.0

        self.t_tweezer_hold = 30.e-3


