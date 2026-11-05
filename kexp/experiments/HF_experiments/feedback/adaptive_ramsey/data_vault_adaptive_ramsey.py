from kexp.experiments.HF_experiments.feedback.data_vault_feedback import DataVault as DataVaultFeedback


class DataVault(DataVaultFeedback):
    def adaptive_ramsey_containers(self, p):
        """Per pulse i: the period from pulse i's start to pulse i+1's start the kernel chose (s;
        the last entry is the plan it would have taken next), the phase offset of pulse i in the
        MODEL convention (rad; the hardware got ramsey_phase_sign * it, wrapped), the quality the
        choice maximized (PHASE_MAXVAR: Var[S_z]; mean/map_par: R), the posterior std (rad/s) and
        mean (rad/s) after pulse i. Per shot: [t_posterior_mu, t_plan_mu, slack_mu] measured in
        initialize_feedback (the same values every shot)."""
        self.ramsey_t_gap = self.add_data_container(p.N_pulses)
        self.ramsey_phase = self.add_data_container(p.N_pulses)
        self.ramsey_Q = self.add_data_container(p.N_pulses)
        self.ramsey_std = self.add_data_container(p.N_pulses)
        self.ramsey_mean = self.add_data_container(p.N_pulses)
        self.ramsey_timing = self.add_data_container(3)
