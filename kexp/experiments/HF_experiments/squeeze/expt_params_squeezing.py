from kexp.config import ExptParams as expt_params_kexp
import numpy as np
from numpy import int64

class ExptParams(expt_params_kexp):
    def __init__(self):
        super().__init__()

        # calibration run 72835
        self.t_img_pulse = 2e-05  # s
        self.amp_imaging = 0.1
        self.v_apd_all_up = -0.31355
        self.v_apd_all_down = -0.2387
        self.n_photons_per_shot = 1071
        # self.std_n_photons_up = 106.31
        # self.std_n_photons_down = 488.11
        # self.std_n_photons_per_shot = 297.21 # avg of up/down
        self.std_n_photons_per_shot = 488.11 # using down std
        self.feedback_measurement_midpoint_fraction = 0.75643