from artiq.experiment import *

class core_ref(EnvExperiment):
    def build(self):
        self.core = self.get_device("core")

        self.t_mu = self.core.seconds_to_mu(self.core.coarse_ref_period)

        print(f"t (s) = {self.core.coarse_ref_period}")
        print(f"t (mu) = {self.t_mu}")

    @kernel
    def run(self):
        pass