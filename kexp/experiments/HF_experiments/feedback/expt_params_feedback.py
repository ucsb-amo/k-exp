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

        self.feedback_fractional_initial_offset = 0.0
        self.feedback_guess_span_Omega = 8.0

        self.t_raman_pulse = self.t_raman_pi_pulse / 2
        self.t_raman_pulse_ideal = 3.576e-06 #3.742e-06

        # calibration run 69942
        # img amp 0.2, pulse time 5.0e-06 s
        # self.frequency_lightshift = 30.e+03  # Hz
        self.frequency_lightshift = 2.797e+04 # 28.8e+03  # Hz

        # calibration run 69990
        # self.t_img_pulse = 5e-06  # s
        # self.amp_imaging = 0.2
        # self.v_apd_all_up = -0.18053
        # self.v_apd_all_down = -0.21441
        # self.n_photons_per_shot = 654.6
        # self.std_n_photons_up = 93.056
        # self.std_n_photons_down = 40.679
        # self.std_n_photons_per_shot = 66.868 # avg of up/down   
        # self.std_n_photons_per_shot = 50. # avg of up/down  
        # self.feedback_measurement_midpoint_fraction = 0.43527

        # calibration run 70019
        # self.t_img_pulse = 7e-06  # s
        # self.amp_imaging = 0.2
        # self.v_apd_all_up = -0.15305
        # self.v_apd_all_down = -0.21326
        # self.n_photons_per_shot = 1043.6
        # self.std_n_photons_up = 146.25
        # self.std_n_photons_down = 80.762
        # self.std_n_photons_per_shot = 100 # avg of up/down
        # self.feedback_measurement_midpoint_fraction = 0.40272

        # calibration run 70025
        self.t_img_pulse = 1e-05  # s
        self.amp_imaging = 0.2
        self.v_apd_all_up = -0.13526
        self.v_apd_all_down = -0.21644
        self.n_photons_per_shot = 1336.9
        # self.std_n_photons_up = 191.57
        # self.std_n_photons_down = 112.63
        self.std_n_photons_per_shot = 152.1# 152.1 # avg of up/down
        self.feedback_measurement_midpoint_fraction = 0.47789

        

        # run 66841 | multi-parameter grid fit result
        self.back_action_coherence = 0.73    

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

        self.delta_t_mu = int64(743)
        # self.delta_t_mu = int64(2000)

        ### other
        self.phase_offset = 0.0

        self.t_tweezer_hold = 30.e-3


