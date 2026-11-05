from kexp.config.data_vault import DataVault as DataVaultKexp
from kexp.experiments.HF_experiments.feedback.expt_params_feedback import ExptParams as ExptParamsFeedback

class DataVault(DataVaultKexp):
    def feedback_data_containers(self, params: ExptParamsFeedback):
        p = params
        self.omega_raman = self.add_data_container(p.N_pulses)
        self.apd = self.add_data_container(p.N_pulses)
        # per shot, written at the top of scan_kernel; older run files lack these two
        self.t_raman_pulse = self.add_data_container(p.N_pulses)
        self.t_raman_pulse_seed = self.add_data_container(1)

        self.s_z = self.add_data_container(p.N_pulses)
        self.t = self.add_data_container(p.N_pulses)

        # row 0 = before the first pulse
        self.omega_raman_mesh = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))
        self.probabilities = self.add_data_container((p.N_pulses + 1, p.feedback_grid_size))