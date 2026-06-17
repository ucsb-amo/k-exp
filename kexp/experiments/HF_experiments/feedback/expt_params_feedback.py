from kexp.config import ExptParams as expt_params_kexp
import numpy as np
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        self.update_raman_frequency_bool = 0
        self.include_photon_noise = 1

        self.feedback_grid_size = 21
        self.N_pulses = 20
        self.feedback_fractional_grid_center_offset = -5.0

        self.feedback_fractional_initial_offset = 0.0
        self.feedback_guess_span_Omega = 8.0

        self.dt_t_raman_pulse_offset = 220.e-9 # non ideal pulse width
        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        self.t_raman_pulse_ideal = 3.727e-06

        # self.t_raman_pulse_ideal = 3.335e-06
        # self.t_raman_pulse = 4.25685e-06
        
        # calibration run 67455
        # img amp 0.2, pulse time 5.0e-06 s
        # self.frequency_lightshift = 3.08e+04# 2.88e+04  # Hz
        # self.frequency_lightshift = 2.886e+04

        # calibration run 69942
        # img amp 0.2, pulse time 5.0e-06 s
        self.frequency_lightshift = 3.38e+04  # Hz

        # calibration run 69744
        # self.t_img_pulse = 5e-06  # s
        # self.amp_imaging = 0.2
        # self.v_apd_all_up = -0.17312
        # self.v_apd_all_down = -0.22099
        # self.n_photons_per_shot = 924.01
        # self.std_n_photons_up = 132.92
        # self.std_n_photons_down = 86.981
        # self.std_n_photons_per_shot = 109.95 # avg of up/down
        # self.std_n_photons_per_shot = 30.
        # self.std_n_photons_per_shot = np.sqrt( self.std_n_photons_up**2 + self.std_n_photons_down**2 )
        # self.feedback_measurement_midpoint_fraction = 0.36462

        # calibration run 69944
        self.t_img_pulse = 5e-06  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.18861
        self.v_apd_all_down = -0.21472
        self.n_photons_per_shot = 489.4
        # self.std_n_photons_up = 118.53
        # self.std_n_photons_down = 75.919
        self.std_n_photons_per_shot = 97.224 # avg of up/down
        self.feedback_measurement_midpoint_fraction = 0.4606

        # run 66841 | multi-parameter grid fit result
        self.back_action_coherence = 0.8206    

        self.feedback_measurement_midpoint_remap_enabled = True

        # run 66415
        self.feedback_apd_map_enabled = False
        self.feedback_apd_map_a = 0.792175653
        self.feedback_apd_map_b = 0.126581972
        self.feedback_apd_map_verbose = True

        ### timing
        self.t_calculation_slack_compensation_mu = int64(0.7 * self.feedback_grid_size * 1.e3) + 20000 if self.feedback_grid_size > 10 else int64(10000)
        self.t_fifo_mu = int64(18416)
        self.t_raman_set_pretrigger_mu = int64(700) & ~7 # int64(1260)

        self.delta_t_mu = int64(702)
        # self.delta_t_mu = int64(2000)

        ### other
        self.phase_offset = 0.0

        self.t_tweezer_hold = 30.e-3


