import numpy as np
from kexp.config.data_vault import DataVault as DataVaultKexp
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback

class DataVault(DataVaultKexp):
    def __init__(self, expt):
        super().__init__(expt)
        
    def feedback_data_containers(self, params: ExptParamsFeedback):
        p = params
        self.omega_raman = self.add_data_container(p.N_pulses+1)
        self.Omega = self.add_data_container(p.N_pulses+1)
        self.apd = self.add_data_container(p.N_pulses)

        self.s_z = self.add_data_container(p.N_pulses+1)
        self.t = self.add_data_container(p.N_pulses+1)

        self.omega_raman_mesh = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))
        self.probabilities = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))