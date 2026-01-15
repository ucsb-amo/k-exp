import numpy as np
from waxx.config.expt_params import ExptParams as ExptParamsWaxx

class ExptParams(ExptParamsWaxx):
    def __init__(self):
        super().__init__()

        self.t_rtio = 8.e-9

        self.N_shots = 1
        self.N_repeats = 1
        self.N_img = 1
        self.N_shots_with_repeats = 1
        self.N_pwa_per_shot = 1

        self.compute_derived()