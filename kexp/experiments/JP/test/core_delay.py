from artiq.experiment import *
from artiq.language import delay, now_mu, at_mu, delay_mu
import numpy as np
from artiq.coredevice.exceptions import RTIOUnderflow
import matplotlib.pyplot as plt

@rpc(flags={"async"})
def aprint(*args):
    print(*args)

class integrator_test(EnvExperiment):

    def prepare(self):
        self.core = self.get_device('core')
        self.ttl = self.get_device('ttl67')

        # Sweep settings in machine units.
        self.t_calc_start_mu = np.int64(0)
        self.t_calc_stop_mu = np.int64(15000)
        self.t_calc_step_mu = np.int64(2000)

        self.t_fifo_start_mu = np.int64(0)
        self.t_fifo_stop_mu = np.int64(15000)
        self.t_fifo_step_mu = np.int64(2000)

        self.n_calc = np.int64(((self.t_calc_stop_mu - self.t_calc_start_mu) // self.t_calc_step_mu) + np.int64(1))
        self.n_fifo = np.int64(((self.t_fifo_stop_mu - self.t_fifo_start_mu) // self.t_fifo_step_mu) + np.int64(1))
        self.n_trials = np.int64(500)

        self.t_calc_values_mu = self.t_calc_start_mu + self.t_calc_step_mu * np.arange(self.n_calc, dtype=np.int64)
        self.t_fifo_values_mu = self.t_fifo_start_mu + self.t_fifo_step_mu * np.arange(self.n_fifo, dtype=np.int64)

        # 1 = success (no underflow), 0 = RTIOUnderflow caught.
        self.success_ok = np.int64(1)
        self.success_fail = np.int64(0)
        self.success_counts = np.zeros((self.n_calc, self.n_fifo), dtype=np.int64)
        # Per-trial threshold for each t_calc (first passing t_fifo, or -1 if none pass).
        self.required_t_fifo_trials_mu = np.full((self.n_calc, self.n_trials), np.int64(-1), dtype=np.int64)

    @rpc(flags={"async"})
    def record_result(self, i_calc, i_fifo, success):
        self.success_counts[i_calc, i_fifo] += success

    @rpc(flags={"async"})
    def record_trial_threshold(self, i_calc, i_trial, required_t_fifo_mu):
        self.required_t_fifo_trials_mu[i_calc, i_trial] = required_t_fifo_mu

    @kernel
    def fake_calc(self,t_computation_time_mu):
        t0 = now_mu()
        slack = t0 - self.core.get_rtio_counter_mu()
        slack0 = slack
        slack_target = slack0 - t_computation_time_mu
        while slack > slack_target:
            slack = t0 - self.core.get_rtio_counter_mu()

    @kernel
    def test_point(self, t_calc_mu, t_fifo_mu):
        self.core.break_realtime()

        t0 = now_mu()
        self.core.wait_until_mu(t0)

        self.fake_calc(t_calc_mu)
        delay_mu(t_fifo_mu + t_calc_mu)
        self.ttl.off()

    @kernel
    def run(self):
        self.core.reset()
        aprint("core_delay: scan started")
        aprint("n_calc=", self.n_calc, "n_fifo=", self.n_fifo, "n_trials=", self.n_trials)

        for i_calc in range(self.n_calc):
            t_calc_mu = self.t_calc_start_mu + i_calc * self.t_calc_step_mu
            aprint("core_delay: t_calc index", i_calc + 1, "/", self.n_calc, "t_calc_mu=", t_calc_mu)
            for i_trial in range(self.n_trials):
                if (i_trial == 0) or ((i_trial + 1) % np.int64(50) == np.int64(0)) or (i_trial + 1 == self.n_trials):
                    aprint("  trial", i_trial + 1, "/", self.n_trials)
                required_t_fifo_mu = np.int64(-1)
                for i_fifo in range(self.n_fifo):
                    t_fifo_mu = self.t_fifo_start_mu + i_fifo * self.t_fifo_step_mu
                    success = self.success_ok
                    try:
                        self.test_point(t_calc_mu, t_fifo_mu)
                    except RTIOUnderflow:
                        success = self.success_fail
                        self.core.break_realtime()
                        self.ttl.off()

                    self.record_result(i_calc, i_fifo, success)
                    if required_t_fifo_mu < np.int64(0) and success == self.success_ok:
                        required_t_fifo_mu = t_fifo_mu

                self.record_trial_threshold(i_calc, i_trial, required_t_fifo_mu)

    def analyze(self):
        success_rate = self.success_counts / float(self.n_trials)
        required_t_fifo_mean_mu = np.full(self.n_calc, np.nan, dtype=np.float64)
        required_t_fifo_std_mu = np.full(self.n_calc, np.nan, dtype=np.float64)

        for i_calc in range(self.n_calc):
            trial_vals = self.required_t_fifo_trials_mu[i_calc]
            valid = trial_vals >= np.int64(0)
            if np.any(valid):
                vals = trial_vals[valid].astype(np.float64)
                required_t_fifo_mean_mu[i_calc] = np.mean(vals)
                required_t_fifo_std_mu[i_calc] = np.std(vals)

        self.set_dataset("core_delay.t_calc_values_mu", self.t_calc_values_mu)
        self.set_dataset("core_delay.t_fifo_values_mu", self.t_fifo_values_mu)
        self.set_dataset("core_delay.n_trials", self.n_trials)
        self.set_dataset("core_delay.success_counts", self.success_counts)
        self.set_dataset("core_delay.success_rate", success_rate)
        self.set_dataset("core_delay.required_t_fifo_trials_mu", self.required_t_fifo_trials_mu)
        self.set_dataset("core_delay.required_t_fifo_mean_mu", required_t_fifo_mean_mu)
        self.set_dataset("core_delay.required_t_fifo_std_mu", required_t_fifo_std_mu)

        print("\ncore_delay scan summary")
        print(f"trials per point: {self.n_trials}")
        print("T_CALC(mu) -> required T_FIFO mean +/- std (mu)")
        for i_calc, t_calc_mu in enumerate(self.t_calc_values_mu):
            mean_val = required_t_fifo_mean_mu[i_calc]
            std_val = required_t_fifo_std_mu[i_calc]
            if np.isnan(mean_val):
                print(f"{t_calc_mu:6d} -> none in scanned range")
            else:
                print(f"{t_calc_mu:6d} -> {mean_val:8.1f} +/- {std_val:6.1f}")

        valid = ~np.isnan(required_t_fifo_mean_mu)
        plt.figure()
        plt.errorbar(
            self.t_calc_values_mu[valid].astype(np.float64),
            required_t_fifo_mean_mu[valid],
            yerr=required_t_fifo_std_mu[valid],
            fmt='o-',
            capsize=3,
        )
        plt.xlabel('t_calc (mu)')
        plt.ylabel('required t_fifo (mu), mean +/- std')
        plt.title('required t_fifo vs t_calc (repeated trials)')
        plt.grid(True)
        plt.tight_layout()
        plt.show()