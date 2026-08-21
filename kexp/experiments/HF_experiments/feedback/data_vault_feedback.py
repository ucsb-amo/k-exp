import numpy as np
from kexp.config.data_vault import DataVault as DataVaultKexp
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback

class DataVault(DataVaultKexp):
    def __init__(self, expt):
        super().__init__(expt)
        
    def feedback_data_containers(self, params: ExptParamsFeedback):
        p = params
        # omega_raman/s_z/t are written once per pulse as `put_data(value, i)` for
        # i in range(N_pulses) (see feedback_loop in base_expt_feedback.py) -- there
        # is no reserved "before first pulse" slot as there is for
        # omega_raman_mesh/probabilities below, so these must match apd's size
        # exactly or their last column is unwritten zero padding.
        self.omega_raman = self.add_data_container(p.N_pulses)
        self.apd = self.add_data_container(p.N_pulses)

        self.s_z = self.add_data_container(p.N_pulses)
        self.t = self.add_data_container(p.N_pulses)

        self.omega_raman_mesh = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))
        self.probabilities = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))